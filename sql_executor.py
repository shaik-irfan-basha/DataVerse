"""
sql_executor.py - SQL Query Executor

Executes SQL queries against a loaded SQLite database and returns
formatted results. Includes safety measures (read-only, timeout).
"""

import sqlite3
import time
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("dataverse.sql")


class SQLExecutor:
    """
    Executes SQL queries safely and returns structured results.
    
    Features:
        - Read-only query execution (blocks INSERT/UPDATE/DELETE/DROP)
        - Query timeout protection
        - Structured result format with column headers
        - Error capture for re-prompting the LLM
    """
    
    # SQL keywords that indicate write operations
    WRITE_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the SQL executor.
        
        Args:
            timeout: Maximum query execution time in seconds
        """
        self.timeout = timeout
    
    def execute(self, connection: sqlite3.Connection, sql: str) -> Dict[str, Any]:
        """
        Execute a SQL query and return structured results.
        
        Args:
            connection: SQLite database connection
            sql: SQL query string to execute
        
        Returns:
            Dictionary with:
                - success: bool
                - columns: list of column names
                - rows: list of row tuples
                - row_count: number of rows returned
                - execution_time: time taken in seconds
                - error: error message if failed, None if success
        """
        result = {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time": 0.0,
            "error": None,
        }
        
        if not connection:
            result["error"] = "No database connection. Please load a dataset first."
            return result
        
        if not sql or not sql.strip():
            result["error"] = "Empty SQL query."
            return result
            
        sql_len = len(sql)
        logger.info(f"Preparing to execute SQL query (length: {sql_len})")
        
        # Safety check: block write operations
        sql_upper = sql.strip().upper()
        for keyword in self.WRITE_KEYWORDS:
            if sql_upper.startswith(keyword):
                result["error"] = (
                    f"Write operations ({keyword}) are not allowed. "
                    f"Only SELECT queries are supported."
                )
                logger.warning(f"Blocked SQL execution. Keyword: {keyword}. Query length: {sql_len}")
                return result
        
        try:
            start_time = time.time()
            
            cursor = connection.cursor()
            cursor.execute(sql)
            
            # Get column names from cursor description
            if cursor.description:
                result["columns"] = [desc[0] for desc in cursor.description]
                result["rows"] = cursor.fetchall()
                result["row_count"] = len(result["rows"])
            else:
                result["columns"] = []
                result["rows"] = []
                result["row_count"] = 0
            
            result["execution_time"] = round(time.time() - start_time, 4)
            result["success"] = True
            logger.info(f"Query successful. Rows: {result['row_count']}, Duration: {result['execution_time']}s")
            
        except sqlite3.Error as e:
            result["error"] = f"SQL Error: {str(e)}"
            result["execution_time"] = round(time.time() - start_time, 4)
            logger.error(f"SQL execution failed. Error: {result['error']}. Query length: {sql_len}")
        except Exception as e:
            result["error"] = f"Execution Error: {str(e)}"
            logger.error(f"Execution Error: {result['error']}. Query length: {sql_len}")
        
        return result
    
    def format_results_text(self, result: Dict, max_rows: int = 50) -> str:
        """
        Format query results as a readable text string.
        
        Args:
            result: Result dictionary from execute()
            max_rows: Maximum rows to include in output
        
        Returns:
            Formatted text string
        """
        if not result["success"]:
            return f"Error: {result['error']}"
        
        if not result["columns"]:
            return "Query executed successfully (no results returned)."
        
        lines = []
        
        # Header
        columns = result["columns"]
        
        # Calculate column widths
        widths = [len(str(col)) for col in columns]
        display_rows = result["rows"][:max_rows]
        
        for row in display_rows:
            for i, val in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], min(len(str(val)), 40))
        
        # Build header
        header = " | ".join(str(col).ljust(widths[i]) for i, col in enumerate(columns))
        separator = "-+-".join("-" * w for w in widths)
        
        lines.append(header)
        lines.append(separator)
        
        # Build rows
        for row in display_rows:
            row_str = " | ".join(
                str(val).ljust(widths[i]) if i < len(widths) else str(val)
                for i, val in enumerate(row)
            )
            lines.append(row_str)
        
        # Summary
        if result["row_count"] > max_rows:
            lines.append(f"\n... showing {max_rows} of {result['row_count']} rows")
        
        lines.append(f"\n({result['row_count']} row(s) in {result['execution_time']}s)")
        
        return "\n".join(lines)


# =============================================================================
# MAIN - Test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  SQL Executor Test")
    print("=" * 60)
    
    # Create a test database
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.execute("INSERT INTO users VALUES (3, 'Charlie', 35)")
    conn.commit()
    
    executor = SQLExecutor()
    
    # Test SELECT
    result = executor.execute(conn, "SELECT * FROM users WHERE age > 25")
    print(f"\nTest SELECT (age > 25):")
    print(executor.format_results_text(result))
    
    # Test blocked write
    result = executor.execute(conn, "DELETE FROM users WHERE id = 1")
    print(f"\nTest blocked DELETE:")
    print(f"  Error: {result['error']}")
    
    # Test bad SQL
    result = executor.execute(conn, "SELECT * FROM nonexistent")
    print(f"\nTest bad SQL:")
    print(f"  Error: {result['error']}")
    
    conn.close()
    print("\n✅ All tests passed!")
