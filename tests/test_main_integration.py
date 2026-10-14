import pytest
import threading
from unittest.mock import patch, MagicMock

# Import the class but we will mock its UI dependency if possible
from main import DataVerseApp
import customtkinter as ctk

# Create root once per session to avoid Tcl init errors on Windows
_global_root = None

def get_root():
    global _global_root
    if _global_root is None:
        _global_root = ctk.CTk()
        _global_root.withdraw()
    return _global_root

@pytest.fixture(autouse=True)
def sync_threads(monkeypatch):
    """Forces threading.Thread to run synchronously."""
    class SynchronousThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon
            
        def start(self):
            self.target(*self.args)
            
    monkeypatch.setattr("main.threading.Thread", SynchronousThread)

@pytest.fixture
def app(monkeypatch):
    """Headless initialization of the main application."""
    monkeypatch.setattr("main.messagebox", MagicMock())
    
    root = get_root()
    application = DataVerseApp(root)
    
    # Patch root.after so it executes synchronously
    def mock_after(ms, func, *args):
        func(*args)
    monkeypatch.setattr(application.root, "after", mock_after)
    
    # Dummy data
    conn = application.connector.get_connection()
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
    application.connector.file_tables["dummy.csv"] = ["test_table"]
    
    yield application
    
    # Clear out text so tests don't leak state
    application.sql_text.delete("1.0", "end")
    application.question_entry.delete("1.0", "end")

def test_manual_valid_sql_accepted(app, monkeypatch):
    mock_execute = MagicMock(return_value={"success": True, "columns": ["id"], "rows": [(1,)], "row_count": 1, "execution_time": 0.05})
    monkeypatch.setattr(app.query_service.executor, "execute", mock_execute)
    
    valid_sql = "SELECT * FROM test_table"
    app.sql_text.insert("1.0", valid_sql)
    
    app.run_sql()
    
    mock_execute.assert_called_once_with(app.connector.get_connection(), valid_sql)
    # UI updates synchronously because of mock_after
    assert "✅" in app.status_label.cget("text")

def test_manual_malicious_sql_rejected(app, monkeypatch):
    mock_execute = MagicMock()
    monkeypatch.setattr(app.query_service.executor, "execute", mock_execute)
    
    malicious_sql = "DROP TABLE test_table"
    app.sql_text.insert("1.0", malicious_sql)
    
    app.run_sql()
    
    mock_execute.assert_not_called()
    assert "❌" in app.status_label.cget("text")
    assert "Validation Failed" in app.answer_label.cget("text")

def test_llm_valid_sql_accepted(app, monkeypatch):
    mock_execute = MagicMock(return_value={"success": True, "columns": ["id"], "rows": [(1,)], "row_count": 1, "execution_time": 0.05})
    monkeypatch.setattr(app.query_service.executor, "execute", mock_execute)
    
    app.query_service.llm_client = app.query_service.llm_client or LLMClientMock()
    app.query_service.llm_client.generate_json = MagicMock(return_value={
        "is_ambiguous": False,
        "sql_query": "SELECT * FROM test_table"
    })
    
    app.question_entry.insert("1.0", "show the test table")
    app.generate_and_run()
    
    # We don't check called_once_with exactly since SQLRecoveryPipeline runs it through executor directly
    # Wait, SQLRecoveryPipeline instantiates a temporary executor or uses the one provided?
    # It uses the one provided! So it should call it!
    assert mock_execute.call_count >= 1
    assert "✅" in app.status_label.cget("text")

def test_llm_malicious_sql_rejected(app, monkeypatch):
    mock_execute = MagicMock()
    monkeypatch.setattr(app.query_service.executor, "execute", mock_execute)
    
    app.query_service.llm_client = app.query_service.llm_client or LLMClientMock()
    app.query_service.llm_client.generate_json = MagicMock(return_value={
        "is_ambiguous": False,
        "sql_query": "DELETE FROM test_table"
    })
    
    app.question_entry.insert("1.0", "delete everything")
    app.generate_and_run()
    
    mock_execute.assert_not_called()
    assert "❌" in app.status_label.cget("text")

class LLMClientMock:
    def generate_json(self, prompt):
        pass
