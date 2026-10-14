import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
import sqlite3

logger = logging.getLogger("dataverse.sql_recovery")

@dataclass
class RecoveryResult:
    success: bool
    final_sql: str
    execution_result: Optional[Dict[str, Any]]
    attempts: int
    retries_used: int
    validation_failures: List[Dict[str, Any]] = field(default_factory=list)
    execution_errors: List[Dict[str, Any]] = field(default_factory=list)
    final_error: Optional[str] = None
    final_outcome: str = ""

def extract_sql_safely(raw_sql: str) -> str:
    """
    Strips surrounding Markdown/code fences.
    Explicitly preserves all internal contents, including semicolons and trailing statements
    so that the SQLValidator can correctly catch MULTI_STATEMENT payloads.
    """
    sql = raw_sql.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
        
    if sql.endswith("```"):
        sql = sql[:-3]
        
    return sql.strip()

class SQLRecoveryPipeline:
    def __init__(self, llm_client, validator, executor, max_retries: int):
        self.llm_client = llm_client
        self.validator = validator
        self.executor = executor
        self.max_retries = max_retries
        
        self.RETRYABLE_VALIDATION_CODES = {"SYNTAX_ERROR", "SCHEMA_ERROR"}
        self.HARD_STOP_CODES = {
            "UNAUTHORIZED_ACTION", "MULTI_STATEMENT", "EMPTY_QUERY",
            "PROGRAMMING_ERROR", "DATABASE_ERROR", "UNKNOWN_ERROR"
        }

    def recover_and_execute(
        self, 
        question: str, 
        initial_raw_sql: str, 
        connector, 
        schema_str: str, 
        ui_callback: Optional[Callable[[int, int, str, str], None]] = None
    ) -> RecoveryResult:
        
        from prompt_builder import build_sql_correction_prompt
        
        result = RecoveryResult(
            success=False,
            final_sql="",
            execution_result=None,
            attempts=0,
            retries_used=0,
            final_outcome="IN_PROGRESS"
        )
        
        current_raw_sql = initial_raw_sql
        
        for attempt in range(self.max_retries + 1):
            result.attempts += 1
            current_sql = extract_sql_safely(current_raw_sql)
            result.final_sql = current_sql
            
            with connector._lock:
                conn = connector.get_connection()
                val_result = self.validator.validate(current_sql, conn)
                
                if not val_result.is_valid:
                    failure_info = {"code": val_result.error_code, "message": val_result.message, "sql": current_sql}
                    result.validation_failures.append(failure_info)
                    
                    if val_result.error_code in self.HARD_STOP_CODES:
                        result.success = False
                        result.final_error = f"Validation Hard Stop [{val_result.stage}]: {val_result.message}"
                        result.final_outcome = "FAILED_SECURITY" if val_result.error_code in ["UNAUTHORIZED_ACTION", "MULTI_STATEMENT"] else "FAILED_VALIDATION_HARD"
                        return result
                        
                    error_msg = f"Validation Failed [{val_result.stage}]: {val_result.message}"
                    
                else:
                    exec_result = self.executor.execute(conn, current_sql)
                    if exec_result["success"]:
                        result.success = True
                        result.execution_result = exec_result
                        result.final_outcome = "SUCCESS_INITIAL" if attempt == 0 else "SUCCESS_RECOVERED"
                        return result
                        
                    error_msg = exec_result["error"]
                    result.execution_errors.append({"error": error_msg, "sql": current_sql})

            # If we reach here, we hit a retryable error (and the lock is now released!)
            if attempt < self.max_retries:
                result.retries_used += 1
                if ui_callback:
                    ui_callback(attempt + 1, self.max_retries, current_sql, error_msg)
                    
                correction_prompt = build_sql_correction_prompt(question, current_sql, error_msg, schema_str)
                current_raw_sql = self.llm_client.generate_sql(correction_prompt)
            else:
                result.success = False
                result.final_error = f"Failed after {self.max_retries} retries. Last error: {error_msg}"
                result.final_outcome = "FAILED_EXHAUSTED"
                return result
                
        return result
