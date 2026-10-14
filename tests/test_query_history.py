import pytest
import os
import tempfile
from query_history import QueryHistory

@pytest.fixture
def temp_history():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    history = QueryHistory(db_path=path)
    yield history
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def test_add_and_retrieve_history(temp_history):
    entry_id = temp_history.add_entry(
        question="Show all users",
        sql_query="SELECT * FROM users",
        success=True,
        row_count=10,
        execution_time=0.012,
        dataset_name="CSV"
    )
    assert entry_id > 0
    
    entries = temp_history.get_recent(limit=10)
    assert len(entries) == 1
    e = entries[0]
    assert e.id == entry_id
    assert e.question == "Show all users"
    assert e.sql_query == "SELECT * FROM users"
    assert e.success is True
    assert e.row_count == 10
    assert e.dataset_name == "CSV"

def test_failed_query_history(temp_history):
    temp_history.add_entry(
        question="Drop everything",
        sql_query="DROP TABLE users",
        success=False,
        error_message="Validation Failed: UNAUTHORIZED",
        dataset_name="Excel"
    )
    entries = temp_history.get_recent(limit=5)
    assert len(entries) == 1
    assert entries[0].success is False
    assert "UNAUTHORIZED" in entries[0].error_message

def test_clear_history(temp_history):
    temp_history.add_entry("Q1", "SQL1", True)
    temp_history.add_entry("Q2", "SQL2", True)
    assert len(temp_history.get_recent()) == 2
    
    success = temp_history.clear_history()
    assert success is True
    assert len(temp_history.get_recent()) == 0

def test_delete_entry(temp_history):
    id1 = temp_history.add_entry("Q1", "SQL1", True)
    id2 = temp_history.add_entry("Q2", "SQL2", True)
    
    assert temp_history.delete_entry(id1) is True
    recent = temp_history.get_recent()
    assert len(recent) == 1
    assert recent[0].id == id2

def test_get_recent_context(temp_history):
    temp_history.add_entry("Q1", "SELECT 1", True)
    temp_history.add_entry("Q2", "SELECT 2", False, error_message="Fail")
    temp_history.add_entry("Q3", "SELECT 3", True)
    
    context = temp_history.get_recent_context(limit=5)
    assert "SELECT 1" in context
    assert "SELECT 3" in context
    assert "SELECT 2" not in context  # Failed queries omitted from prompt context
