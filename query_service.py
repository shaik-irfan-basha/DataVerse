"""
query_service.py - Headless Business Orchestration Layer for DataVerse

Orchestrates data ingestion, natural-language query processing, SQL validation,
recovery execution, query history tracking, data profiling, visualization, and export.
Completely decoupled from any UI framework.
"""

import logging
import time
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
import config

from data_connector import DataConnector
from sql_validator import SQLValidator
from sql_executor import SQLExecutor
from sql_recovery import SQLRecoveryPipeline
from llm_client import LLMClient
from clarification_engine import build_analysis_prompt
from query_history import QueryHistory, HistoryEntry
from data_profiler import DataProfiler, TableProfile
from export_engine import ExportEngine
from chart_engine import ChartEngine
from suggested_questions import SuggestedQuestionsGenerator

logger = logging.getLogger("dataverse.query_service")

@dataclass
class QueryResponse:
    status: str  # "SUCCESS", "ERROR", "CLARIFICATION_REQUIRED"
    sql: str = ""
    data: Optional[Dict] = None
    clarification_question: str = ""
    clarification_options: List[str] = field(default_factory=list)
    error_message: str = ""

class QueryService:
    def __init__(self, connector: DataConnector, history: Optional[QueryHistory] = None):
        self.connector = connector
        self.executor = SQLExecutor()
        self.validator = SQLValidator()
        self.llm_client = None  # Lazy load
        self.history = history or QueryHistory()

    def load_file(self, file_path: str) -> List[str]:
        """
        Loads data into the connector. Returns a list of table names.
        Raises exception on failure.
        """
        return self.connector.load_file(file_path)

    def execute_manual_sql(self, sql: str) -> Dict:
        """
        Validates and executes manual SQL. 
        Returns the execution result dict format matching SQLExecutor.
        Records outcome to query history.
        """
        start_time = time.time()
        with self.connector._lock:
            conn = self.connector.get_connection()
            
            # 1. Validate
            val_result = self.validator.validate(sql, conn)
            if not val_result.is_valid:
                err_msg = f"Validation Failed [{val_result.stage}]: {val_result.message}"
                self.history.add_entry(
                    question="Manual SQL Execution",
                    sql_query=sql,
                    success=False,
                    error_message=err_msg,
                    dataset_name=self.connector.file_type
                )
                return {
                    "success": False,
                    "error": err_msg
                }
            
            # 2. Execute
            exec_res = self.executor.execute(conn, sql)
            
            # Record history
            if exec_res.get("success"):
                self.history.add_entry(
                    question="Manual SQL Execution",
                    sql_query=sql,
                    success=True,
                    row_count=exec_res.get("row_count", 0),
                    execution_time=exec_res.get("execution_time", round(time.time() - start_time, 4)),
                    dataset_name=self.connector.file_type
                )
            else:
                self.history.add_entry(
                    question="Manual SQL Execution",
                    sql_query=sql,
                    success=False,
                    error_message=exec_res.get("error", "Execution failed"),
                    dataset_name=self.connector.file_type
                )
            return exec_res

    def query(self, 
              question: str, 
              clarification_history: str = "",
              retry_callback: Optional[Callable[[int, int, str, str], None]] = None) -> QueryResponse:
        """
        Main AI query orchestration.
        Handles prompt generation, LLM querying, clarification detection, recovery,
        and automatic history recording.
        """
        start_time = time.time()
        try:
            if self.llm_client is None:
                self.llm_client = LLMClient()
                
            schema_str = self.connector.get_schema_string()
            sample_data = self.connector.get_sample_data_string(config.MAX_SAMPLE_ROWS)

            prompt = build_analysis_prompt(question, schema_str, sample_data, clarification_history)
            
            analysis = self.llm_client.generate_json(prompt)
            
            if analysis.get("is_ambiguous", False):
                cq = analysis.get("clarification_question", "Please clarify.")
                opts = analysis.get("options", [])
                return QueryResponse(
                    status="CLARIFICATION_REQUIRED",
                    clarification_question=cq,
                    clarification_options=opts
                )
            
            sql_raw = analysis.get("sql_query", "")
            if not sql_raw:
                err_msg = "No SQL generated by the model."
                self.history.add_entry(
                    question=question,
                    sql_query="",
                    success=False,
                    error_message=err_msg,
                    dataset_name=self.connector.file_type
                )
                return QueryResponse(
                    status="ERROR",
                    error_message=err_msg
                )
                
            pipeline = SQLRecoveryPipeline(
                llm_client=self.llm_client,
                validator=self.validator,
                executor=self.executor,
                max_retries=getattr(config, "MAX_SQL_RETRIES", 2)
            )
            
            recovery_result = pipeline.recover_and_execute(
                question=question,
                initial_raw_sql=sql_raw,
                connector=self.connector,
                schema_str=schema_str,
                ui_callback=retry_callback
            )
            
            elapsed = round(time.time() - start_time, 4)
            
            if recovery_result.success:
                self.history.add_entry(
                    question=question,
                    sql_query=recovery_result.final_sql,
                    success=True,
                    row_count=recovery_result.execution_result.get("row_count", 0),
                    execution_time=recovery_result.execution_result.get("execution_time", elapsed),
                    dataset_name=self.connector.file_type
                )
                return QueryResponse(
                    status="SUCCESS",
                    sql=recovery_result.final_sql,
                    data=recovery_result.execution_result
                )
            else:
                self.history.add_entry(
                    question=question,
                    sql_query=recovery_result.final_sql,
                    success=False,
                    error_message=recovery_result.final_error,
                    dataset_name=self.connector.file_type
                )
                return QueryResponse(
                    status="ERROR",
                    sql=recovery_result.final_sql,
                    data={
                        "success": False,
                        "error": recovery_result.final_error
                    },
                    error_message=recovery_result.final_error
                )
                
        except Exception as e:
            logger.error(f"Error during query execution: {e}")
            self.history.add_entry(
                question=question,
                sql_query="",
                success=False,
                error_message=str(e),
                dataset_name=self.connector.file_type
            )
            return QueryResponse(
                status="ERROR",
                error_message=str(e)
            )

    # -------------------------------------------------------------------------
    # Extended Capabilities (Phases 8, 9, 10)
    # -------------------------------------------------------------------------
    
    def get_history(self, limit: int = 50) -> List[HistoryEntry]:
        """Returns recent query history."""
        return self.history.get_recent(limit=limit)

    def clear_history(self) -> bool:
        """Clears query history database."""
        return self.history.clear_history()

    def profile_table(self, table_name: str) -> TableProfile:
        """Profiles a specific loaded table."""
        return DataProfiler.profile_table(self.connector, table_name)

    def profile_all_tables(self) -> Dict[str, TableProfile]:
        """Profiles all loaded tables."""
        return DataProfiler.profile_all_tables(self.connector)

    def get_suggested_questions(self, max_questions: int = 5) -> List[str]:
        """Generates smart schema-aware starter questions."""
        return SuggestedQuestionsGenerator.generate(self.connector, max_questions=max_questions)

    def export_results(self, columns: List[str], rows: List[tuple], file_path: str, format_type: str = "csv") -> str:
        """Exports query results to CSV, Excel, or JSON."""
        fmt = format_type.lower()
        if fmt == "excel" or fmt == "xlsx":
            return ExportEngine.export_to_excel(columns, rows, file_path)
        elif fmt == "json":
            return ExportEngine.export_to_json(columns, rows, file_path)
        else:
            return ExportEngine.export_to_csv(columns, rows, file_path)

    def generate_chart(self, columns: List[str], rows: List[tuple], chart_type: str = "auto", title: str = ""):
        """Generates a Matplotlib Figure visualization of the results."""
        return ChartEngine.create_figure(columns, rows, chart_type=chart_type, title=title)
