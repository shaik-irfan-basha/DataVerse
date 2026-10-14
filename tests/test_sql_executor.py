import pytest
import sqlite3
from sql_executor import SQLExecutor

@pytest.fixture
def mock_db_connection():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE mock_table (id INTEGER, val TEXT)")
    cursor.execute("INSERT INTO mock_table VALUES (1, 'A')")
    cursor.execute("INSERT INTO mock_table VALUES (2, 'B')")
    conn.commit()
    return conn

def test_execute_valid_select(mock_db_connection):
    executor = SQLExecutor()
    result = executor.execute(mock_db_connection, "SELECT * FROM mock_table")
    
    assert result["success"] is True
    assert result["row_count"] == 2
    assert result["columns"] == ["id", "val"]
    assert len(result["rows"]) == 2
    assert result["error"] is None

def test_execute_blocked_writes(mock_db_connection):
    executor = SQLExecutor()
    blocked_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]
    
    for kw in blocked_keywords:
        sql = f"{kw} INTO mock_table VALUES (3, 'C')"
        if kw == "UPDATE":
            sql = f"{kw} mock_table SET val='C'"
        elif kw in ["DROP", "CREATE", "ALTER", "TRUNCATE"]:
            sql = f"{kw} TABLE mock_table"
            
        result = executor.execute(mock_db_connection, sql)
        
        assert result["success"] is False
        assert result["error"] is not None
        assert kw in result["error"], f"Expected blocked keyword {kw} in error message"

def test_execute_invalid_sql(mock_db_connection):
    executor = SQLExecutor()
    result = executor.execute(mock_db_connection, "SELECT * FRO mock_table") # typo FRO
    
    assert result["success"] is False
    assert result["error"] is not None
    assert "syntax error" in result["error"].lower()

def test_execute_empty_sql(mock_db_connection):
    executor = SQLExecutor()
    result = executor.execute(mock_db_connection, "   ")
    
    assert result["success"] is False
    assert "empty" in result["error"].lower()
