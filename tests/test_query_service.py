import pytest
from unittest.mock import MagicMock
from query_service import QueryService
from data_connector import DataConnector

@pytest.fixture
def service():
    connector = DataConnector()
    # Create an in-memory db with a dummy table
    conn = connector.get_connection()
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
    connector.file_tables["dummy"] = ["test_table"]
    
    svc = QueryService(connector)
    # Mock LLM Client
    svc.llm_client = MagicMock()
    
    # Spy on executor
    svc.executor.execute = MagicMock(wraps=svc.executor.execute)
    return svc

def test_manual_sql_success(service):
    res = service.execute_manual_sql("SELECT * FROM test_table")
    assert res["success"] is True
    service.executor.execute.assert_called_once()

def test_manual_sql_invalid_syntax(service):
    res = service.execute_manual_sql("SELECT * FRO test_table")
    assert res["success"] is False
    assert "Validation Failed" in res["error"]
    service.executor.execute.assert_not_called()

def test_manual_sql_unauthorized(service):
    res = service.execute_manual_sql("DROP TABLE test_table")
    assert res["success"] is False
    assert "UNAUTHORIZED" in res["error"] or "Validation Failed" in res["error"]
    service.executor.execute.assert_not_called()

def test_manual_sql_multi_statement(service):
    res = service.execute_manual_sql("SELECT * FROM test_table; SELECT * FROM test_table;")
    assert res["success"] is False
    assert "MULTI_STATEMENT" in res["error"] or "Validation Failed" in res["error"]
    service.executor.execute.assert_not_called()

def test_generated_sql_success(service):
    service.llm_client.generate_json.return_value = {
        "is_ambiguous": False,
        "sql_query": "SELECT * FROM test_table"
    }
    
    resp = service.query("show test table")
    assert resp.status == "SUCCESS"
    assert resp.sql == "SELECT * FROM test_table"
    assert resp.data["success"] is True
    service.executor.execute.assert_called_once()

def test_generated_sql_validation_rejection(service):
    # Tests that the recovery pipeline correctly blocks and doesn't execute malicious SQL
    service.llm_client.generate_json.return_value = {
        "is_ambiguous": False,
        "sql_query": "DROP TABLE test_table"
    }
    
    resp = service.query("drop everything")
    assert resp.status == "ERROR"
    assert "Validation" in resp.error_message or "UNAUTHORIZED" in resp.error_message
    service.executor.execute.assert_not_called()

def test_clarification_required(service):
    service.llm_client.generate_json.return_value = {
        "is_ambiguous": True,
        "clarification_question": "Which table?",
        "options": ["A", "B"]
    }
    
    resp = service.query("show it")
    assert resp.status == "CLARIFICATION_REQUIRED"
    assert resp.clarification_question == "Which table?"
    assert resp.clarification_options == ["A", "B"]
    service.executor.execute.assert_not_called()

def test_clarification_history_preservation(service):
    service.llm_client.generate_json.return_value = {
        "is_ambiguous": False,
        "sql_query": "SELECT * FROM test_table"
    }
    
    history = "AI: Which table?\nUser: A\n\n"
    resp = service.query("show it", clarification_history=history)
    
    assert resp.status == "SUCCESS"
    
    # Verify the history was passed into the prompt correctly
    import query_service as qs
    original_build = qs.build_analysis_prompt
    
    with pytest.MonkeyPatch().context() as m:
        mock_build = MagicMock(wraps=original_build)
        m.setattr(qs, "build_analysis_prompt", mock_build)
        
        service.query("show it", clarification_history=history)
        
        # Check that clarification_history was used
        args, kwargs = mock_build.call_args
        assert history in args or kwargs.get("clarification_history") == history or (len(args) > 3 and args[3] == history)

def test_recovery_behavior(service):
    # First LLM call yields bad SQL.
    # Second LLM call yields good SQL.
    service.llm_client.generate_json.return_value = {
        "is_ambiguous": False,
        "sql_query": "SELECT * FRO test_table" # syntax error
    }
    service.llm_client.generate_sql.return_value = "SELECT * FROM test_table" # recovery SQL
    
    # We need a custom mock for generate_sql because it returns a string directly
    
    resp = service.query("show test table")
    assert resp.status == "SUCCESS"
    assert resp.sql == "SELECT * FROM test_table"
    
    # Ensure it was called for recovery
    service.llm_client.generate_sql.assert_called_once()
    service.executor.execute.assert_called_once() # execute only called on the valid SQL

def test_no_gui_dependency():
    # Read query_service.py and ensure no tkinter
    with open('query_service.py', 'r') as f:
        content = f.read()
    assert 'tkinter' not in content.lower()
    assert 'customtkinter' not in content.lower()

def test_query_service_history_and_export(service):
    # Execute manual SQL
    res = service.execute_manual_sql("SELECT * FROM test_table")
    assert res["success"] is True
    
    # Check history was recorded
    history = service.get_history(limit=5)
    assert len(history) >= 1
    assert history[0].sql_query == "SELECT * FROM test_table"
    
    # Test export
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    try:
        exported = service.export_results(["id"], [(1,)], path, "csv")
        assert os.path.exists(exported)
    finally:
        if os.path.exists(path):
            os.remove(path)
            
    # Test chart generation
    fig = service.generate_chart(["id"], [(1,)])
    assert fig is not None

def test_query_service_profiling_and_suggestions(service):
    # Profile table
    profile = service.profile_table("test_table")
    assert profile.table_name == "test_table"
    assert profile.total_columns == 2
    
    # Profile all
    all_profiles = service.profile_all_tables()
    assert "test_table" in all_profiles
    
    # Suggested questions
    questions = service.get_suggested_questions(max_questions=3)
    assert len(questions) > 0
