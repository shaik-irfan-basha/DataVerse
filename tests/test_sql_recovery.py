import pytest
from unittest.mock import MagicMock
from sql_recovery import SQLRecoveryPipeline, extract_sql_safely
from sql_validator import ValidationResult

class MockConnector:
    def __init__(self):
        class MockLock:
            def __enter__(self): pass
            def __exit__(self, exc_type, exc_val, exc_tb): pass
        self._lock = MockLock()
    def get_connection(self):
        return MagicMock()

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    return llm

@pytest.fixture
def mock_validator():
    val = MagicMock()
    return val

@pytest.fixture
def mock_executor():
    exc = MagicMock()
    return exc

@pytest.fixture
def pipeline(mock_llm, mock_validator, mock_executor):
    return SQLRecoveryPipeline(mock_llm, mock_validator, mock_executor, max_retries=2)

@pytest.fixture
def connector():
    return MockConnector()

def test_extract_sql_safely():
    # Markdown wrapped
    assert extract_sql_safely("```sql\nSELECT * FROM t;\n```") == "SELECT * FROM t;"
    # Just backticks
    assert extract_sql_safely("```\nSELECT * FROM t;\n```") == "SELECT * FROM t;"
    # Multi-statement preserved
    assert extract_sql_safely("SELECT * FROM t; DROP TABLE t;") == "SELECT * FROM t; DROP TABLE t;"
    # Multi-statement inside markdown preserved
    assert extract_sql_safely("```sql\nSELECT * FROM t; DROP TABLE t;\n```") == "SELECT * FROM t; DROP TABLE t;"

def test_initial_success(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(True, "Complete")
    mock_executor.execute.return_value = {"success": True, "rows": []}
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1;", connector, "schema")
    
    assert result.success is True
    assert result.final_outcome == "SUCCESS_INITIAL"
    assert result.retries_used == 0
    mock_llm.generate_sql.assert_not_called()

def test_execution_failure_recovered_success(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(True, "Complete")
    
    # First executor fails, second succeeds
    mock_executor.execute.side_effect = [
        {"success": False, "error": "Division by zero"},
        {"success": True, "rows": []}
    ]
    mock_llm.generate_sql.return_value = "SELECT 2;"
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1/0;", connector, "schema")
    
    assert result.success is True
    assert result.final_outcome == "SUCCESS_RECOVERED"
    assert result.retries_used == 1
    assert mock_llm.generate_sql.call_count == 1
    assert mock_executor.execute.call_count == 2
    assert len(result.execution_errors) == 1

def test_execution_failure_two_corrections_success(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(True, "Complete")
    mock_executor.execute.side_effect = [
        {"success": False, "error": "Err1"},
        {"success": False, "error": "Err2"},
        {"success": True, "rows": []}
    ]
    mock_llm.generate_sql.side_effect = ["SELECT 2;", "SELECT 3;"]
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1/0;", connector, "schema")
    
    assert result.success is True
    assert result.retries_used == 2
    assert mock_llm.generate_sql.call_count == 2
    assert mock_executor.execute.call_count == 3
    assert len(result.execution_errors) == 2

def test_retry_limit_enforcement(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(True, "Complete")
    mock_executor.execute.return_value = {"success": False, "error": "Err"}
    mock_llm.generate_sql.return_value = "SELECT 2;"
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1;", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_EXHAUSTED"
    assert result.retries_used == 2
    assert mock_executor.execute.call_count == 3  # Initial + 2 retries

def test_schema_validation_failure_recovered(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.side_effect = [
        ValidationResult(False, "Schema", "SCHEMA_ERROR", "No such table"),
        ValidationResult(True, "Complete")
    ]
    mock_executor.execute.return_value = {"success": True, "rows": []}
    mock_llm.generate_sql.return_value = "SELECT * FROM real_table;"
    
    result = pipeline.recover_and_execute("Q?", "SELECT * FROM fake;", connector, "schema")
    
    assert result.success is True
    assert result.retries_used == 1
    assert mock_executor.execute.call_count == 1 # First one bypassed executor entirely
    assert len(result.validation_failures) == 1

def test_syntax_validation_failure_recovered(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.side_effect = [
        ValidationResult(False, "Syntax", "SYNTAX_ERROR", "Syntax err"),
        ValidationResult(True, "Complete")
    ]
    mock_executor.execute.return_value = {"success": True, "rows": []}
    mock_llm.generate_sql.return_value = "SELECT 1;"
    
    result = pipeline.recover_and_execute("Q?", "SELET 1;", connector, "schema")
    
    assert result.success is True
    assert result.retries_used == 1

def test_unauthorized_action_immediate_stop(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(False, "Auth", "UNAUTHORIZED_ACTION", "Deny")
    
    result = pipeline.recover_and_execute("Q?", "DROP TABLE users;", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_SECURITY"
    assert result.retries_used == 0
    mock_llm.generate_sql.assert_not_called()
    mock_executor.execute.assert_not_called()

def test_multi_statement_immediate_stop(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(False, "Stmt", "MULTI_STATEMENT", "Multiple")
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1; SELECT 2;", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_SECURITY"
    assert result.retries_used == 0
    mock_llm.generate_sql.assert_not_called()
    mock_executor.execute.assert_not_called()

def test_empty_query_immediate_stop(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(False, "Basic", "EMPTY_QUERY", "Empty")
    
    result = pipeline.recover_and_execute("Q?", "", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_VALIDATION_HARD"
    assert result.retries_used == 0

def test_database_error_no_retry(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.return_value = ValidationResult(False, "DB", "DATABASE_ERROR", "Generic")
    
    result = pipeline.recover_and_execute("Q?", "SELECT 1;", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_VALIDATION_HARD"
    assert result.retries_used == 0
    mock_llm.generate_sql.assert_not_called()

def test_malicious_corrected_sql_rejected(pipeline, mock_validator, mock_executor, connector, mock_llm):
    mock_validator.validate.side_effect = [
        ValidationResult(False, "Schema", "SCHEMA_ERROR", "No table"),
        ValidationResult(False, "Auth", "UNAUTHORIZED_ACTION", "Deny")
    ]
    mock_llm.generate_sql.return_value = "DROP TABLE users;"
    
    result = pipeline.recover_and_execute("Q?", "SELECT * FROM fake;", connector, "schema")
    
    assert result.success is False
    assert result.final_outcome == "FAILED_SECURITY"
    assert result.retries_used == 1
    # Executor should NEVER be called on either attempt
    mock_executor.execute.assert_not_called()
