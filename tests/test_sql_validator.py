import pytest
import sqlite3
from sql_validator import SQLValidator

@pytest.fixture
def mock_db_connection():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER, name TEXT, role TEXT)")
    cursor.execute("CREATE TABLE orders (id INTEGER, user_id INTEGER, amount REAL)")
    conn.commit()
    return conn

@pytest.fixture
def validator():
    return SQLValidator()

def test_valid_select(validator, mock_db_connection):
    sql = "SELECT * FROM users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is True

def test_valid_complex_select(validator, mock_db_connection):
    sql = """
    WITH top_users AS (
        SELECT user_id, SUM(amount) as total FROM orders GROUP BY user_id
    )
    SELECT u.name, t.total
    FROM users u
    JOIN top_users t ON u.id = t.user_id
    WHERE t.total > 100
    ORDER BY t.total DESC
    LIMIT 10
    """
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is True

def test_valid_union(validator, mock_db_connection):
    sql = "SELECT id FROM users UNION ALL SELECT user_id FROM orders"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is True

def test_quoted_identifiers(validator, mock_db_connection):
    sql = 'SELECT "id", "name" FROM "users"'
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is True

def test_reject_insert(validator, mock_db_connection):
    sql = "INSERT INTO users (id, name, role) VALUES (1, 'Alice', 'admin')"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_update(validator, mock_db_connection):
    sql = "UPDATE users SET role = 'admin'"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_delete(validator, mock_db_connection):
    sql = "DELETE FROM users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_drop(validator, mock_db_connection):
    sql = "DROP TABLE users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_attach(validator, mock_db_connection):
    sql = "ATTACH DATABASE 'file.db' AS ext"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_multi_statement(validator, mock_db_connection):
    sql = "SELECT * FROM users; DROP TABLE orders"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.error_code == "MULTI_STATEMENT"

def test_reject_cte_masking(validator, mock_db_connection):
    # This tries to mask a destructive operation by starting with WITH
    sql = "WITH safe AS (SELECT * FROM users) DELETE FROM orders"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_whitespace_bypass(validator, mock_db_connection):
    sql = "   \n\tUPDATE users SET name='hacked'"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_comment_bypass(validator, mock_db_connection):
    sql = "-- totally innocent\nDELETE FROM users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Statement Authorization"

def test_reject_hallucinated_table(validator, mock_db_connection):
    sql = "SELECT * FROM nonexistent_table"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Schema Validation"
    assert "no such table" in result.message

def test_reject_hallucinated_column(validator, mock_db_connection):
    sql = "SELECT fake_column FROM users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Schema Validation"
    assert "no such column" in result.message

def test_reject_syntax_error(validator, mock_db_connection):
    sql = "SELECT * FRO users"
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.stage == "Syntax Validation"

def test_reject_empty_query(validator, mock_db_connection):
    sql = "   "
    result = validator.validate(sql, mock_db_connection)
    assert result.is_valid is False
    assert result.error_code == "EMPTY_QUERY"

def test_authorizer_is_restored(validator, mock_db_connection):
    sql = "SELECT * FROM users"
    validator.validate(sql, mock_db_connection)
    
    # Try to execute a dangerous query directly to prove the authorizer was removed
    # If the authorizer was still attached, this would raise a DatabaseError "not authorized"
    mock_db_connection.execute("CREATE TABLE temp_test (id INTEGER)")
    mock_db_connection.commit()
    # It succeeded, meaning authorizer is safely detached.

def test_integration_spy_blocks_executor(monkeypatch, validator, mock_db_connection):
    """Proves that a rejected query never reaches SQLExecutor."""
    from sql_executor import SQLExecutor
    from unittest.mock import MagicMock
    
    executor = SQLExecutor()
    # Spy on the execute method
    mock_execute = MagicMock(return_value={"success": True})
    monkeypatch.setattr(executor, "execute", mock_execute)
    
    # Inject into a simulated flow
    sql = "DELETE FROM users"
    val_result = validator.validate(sql, mock_db_connection)
    if val_result.is_valid:
        executor.execute(mock_db_connection, sql)
        
    # The mock should NOT have been called
    mock_execute.assert_not_called()
    
    # Now try a valid query
    sql_valid = "SELECT * FROM users"
    val_result2 = validator.validate(sql_valid, mock_db_connection)
    if val_result2.is_valid:
        executor.execute(mock_db_connection, sql_valid)
        
    mock_execute.assert_called_once_with(mock_db_connection, sql_valid)
