import sqlite3
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("dataverse.sql_validator")

class ValidationResult:
    def __init__(self, is_valid: bool, stage: str, error_code: Optional[str] = None, message: Optional[str] = None):
        self.is_valid = is_valid
        self.stage = stage
        self.error_code = error_code
        self.message = message
        
    def __str__(self):
        if self.is_valid:
            return "Valid"
        return f"[{self.stage}] {self.error_code}: {self.message}"

class SQLValidator:
    """
    Dedicated SQL Validation Layer.
    Uses SQLite's native parser and authorizer to ensure dialect-accurate validation
    and a strong database-enforced authorization boundary.
    """
    
    # Explicit deny list for dangerous authorizer actions
    DENY_LIST = {
        sqlite3.SQLITE_INSERT, 
        sqlite3.SQLITE_UPDATE, 
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_TABLE, 
        sqlite3.SQLITE_CREATE_INDEX, 
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE, 
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER, 
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER, 
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_DROP_TABLE, 
        sqlite3.SQLITE_DROP_INDEX, 
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE, 
        sqlite3.SQLITE_DROP_TEMP_TRIGGER, 
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER, 
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_ALTER_TABLE, 
        sqlite3.SQLITE_ATTACH, 
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
        # Transaction actions aren't directly destructive but shouldn't be allowed in a single SELECT context
        sqlite3.SQLITE_TRANSACTION
    }
    
    @classmethod
    def _authorizer_callback(cls, action_code: int, arg1: str, arg2: str, dbname: str, source: str) -> int:
        if action_code in cls.DENY_LIST:
            logger.warning(f"Authorizer rejected action code: {action_code} (arg1={arg1}, arg2={arg2})")
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def validate(self, sql: str, connection: sqlite3.Connection) -> ValidationResult:
        """
        Validates the SQL query against the provided connection.
        Must be called with the active database connection. 
        Connection locking should be handled by the caller.
        """
        if not sql or not sql.strip():
            return ValidationResult(False, "Basic Cleansing", "EMPTY_QUERY", "SQL query is empty.")
            
        # Temporarily install the authorizer
        connection.set_authorizer(self._authorizer_callback)
        
        try:
            cursor = connection.cursor()
            # Prefixing with EXPLAIN forces SQLite to prepare/compile the statement
            # against the actual schema without executing it.
            cursor.execute(f"EXPLAIN {sql}")
            
        except sqlite3.ProgrammingError as e:
            msg = str(e).lower()
            if "one statement at a time" in msg or "multiple statements" in msg:
                return ValidationResult(
                    False, 
                    "Statement Validation", 
                    "MULTI_STATEMENT", 
                    "Multiple SQL statements are not allowed."
                )
            return ValidationResult(False, "Execution Planning", "PROGRAMMING_ERROR", str(e))
            
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg:
                return ValidationResult(
                    False, 
                    "Statement Authorization", 
                    "UNAUTHORIZED_ACTION", 
                    f"Attempted forbidden operation. Only read-only queries are permitted."
                )
            elif "syntax error" in msg:
                return ValidationResult(
                    False, 
                    "Syntax Validation", 
                    "SYNTAX_ERROR", 
                    f"Syntax error: {msg}"
                )
            elif "no such table" in msg or "no such column" in msg:
                return ValidationResult(
                    False, 
                    "Schema Validation", 
                    "SCHEMA_ERROR", 
                    f"Schema error: {msg}"
                )
            else:
                return ValidationResult(
                    False, 
                    "Execution Planning", 
                    "DATABASE_ERROR", 
                    f"Database error: {msg}"
                )
        except Exception as e:
            return ValidationResult(False, "Validation Error", "UNKNOWN_ERROR", str(e))
            
        finally:
            # ALWAYS remove the authorizer
            connection.set_authorizer(None)
            
        return ValidationResult(True, "Validation Complete")
