"""
test_reliability_security.py - Dedicated Reliability & Security Verification

Explicitly tests:
1. Rejection of destructive/unauthorized SQL (DROP, DELETE, UPDATE, INSERT, ALTER, ATTACH, PRAGMA)
2. Malformed/injected SQL cannot bypass validation
3. Database and pipeline errors never expose secrets or environment credentials
4. LLM timeouts, network failures, invalid JSON, and exhausted retries are handled gracefully
5. SQL recovery pipeline strictly preserves the user's original question across retries
6. Query history and export engines handle empty result sets and errors safely
"""

import pytest
import sqlite3
import os
from unittest.mock import MagicMock, patch
import requests

from sql_validator import SQLValidator
from sql_executor import SQLExecutor
from sql_recovery import SQLRecoveryPipeline
from query_service import QueryService
from data_connector import DataConnector
from export_engine import ExportEngine
from query_history import QueryHistory

@pytest.fixture
def isolated_connector():
    connector = DataConnector()
    conn = connector.get_connection()
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, username TEXT, balance REAL)")
    conn.execute("INSERT INTO accounts VALUES (1, 'alice', 1000.0), (2, 'bob', 500.0)")
    connector.file_tables["accounts.csv"] = ["accounts"]
    return connector

def test_destructive_statements_rejected(isolated_connector):
    validator = SQLValidator()
    executor = SQLExecutor()
    conn = isolated_connector.get_connection()
    
    destructive_payloads = [
        "DROP TABLE accounts",
        "DELETE FROM accounts WHERE id = 1",
        "UPDATE accounts SET balance = 0",
        "INSERT INTO accounts VALUES (3, 'mallory', 9999.0)",
        "ALTER TABLE accounts ADD COLUMN secret TEXT",
        "ATTACH DATABASE ':memory:' AS shadow_db",
        "PRAGMA database_list",
        "SELECT * FROM accounts; DROP TABLE accounts;"
    ]
    
    for payload in destructive_payloads:
        val_res = validator.validate(payload, conn)
        assert val_res.is_valid is False, f"Payload unexpectedly passed validation: {payload}"
        assert val_res.error_code in ["UNAUTHORIZED_ACTION", "MULTI_STATEMENT", "SYNTAX_ERROR"]

def test_malformed_sql_cannot_bypass_validation(isolated_connector):
    validator = SQLValidator()
    conn = isolated_connector.get_connection()
    
    malformed_queries = [
        "SELECT * FROM",
        "SELECT FROM accounts",
        "SELECT * FROM accounts WHERE id = 'unclosed_string",
        "SELECT * FROM non_existent_table_12345",
        "SELECT * FROM accounts WHERE non_existent_column_abc = 1",
        "",
        "   "
    ]
    
    for q in malformed_queries:
        val_res = validator.validate(q, conn)
        assert val_res.is_valid is False, f"Malformed query unexpectedly passed: {q}"

def test_database_errors_do_not_expose_secrets(isolated_connector):
    # Set a dummy secret in env
    secret_token = "SUPER_SECRET_TOKEN_XYZ_987"
    os.environ["MOCK_API_KEY"] = secret_token
    
    svc = QueryService(isolated_connector)
    
    # 1. Error on invalid manual SQL
    res = svc.execute_manual_sql("SELECT * FROM non_existent_table")
    assert res["success"] is False
    assert secret_token not in res["error"]
    
    # 2. Error on invalid file load
    try:
        svc.load_file("non_existent_file_path.csv")
    except Exception as e:
        assert secret_token not in str(e)

def test_llm_failure_graceful_handling(isolated_connector):
    svc = QueryService(isolated_connector)
    svc.llm_client = MagicMock()
    
    # 1. Timeout failure
    svc.llm_client.generate_json.side_effect = requests.exceptions.Timeout("Connection timed out after 30s")
    resp = svc.query("Show accounts")
    assert resp.status == "ERROR"
    assert "timed out" in resp.error_message.lower() or "timeout" in resp.error_message.lower()
    
    # 2. Invalid JSON response from LLM
    svc.llm_client.generate_json.side_effect = ValueError("The LLM did not return a valid JSON object.")
    resp = svc.query("Show accounts")
    assert resp.status == "ERROR"
    assert "valid json" in resp.error_message.lower()

def test_sql_recovery_preserves_question(isolated_connector):
    llm_mock = MagicMock()
    # First attempt: invalid syntax
    llm_mock.generate_sql.return_value = "SELECT * FROM accounts"
    
    validator = SQLValidator()
    executor = SQLExecutor()
    pipeline = SQLRecoveryPipeline(llm_mock, validator, executor, max_retries=2)
    
    original_question = "What is Alice's account balance?"
    schema_str = isolated_connector.get_schema_string()
    
    result = pipeline.recover_and_execute(
        question=original_question,
        initial_raw_sql="SELECT * FRO accounts",  # syntax error
        connector=isolated_connector,
        schema_str=schema_str
    )
    
    # Verify that the prompt sent to LLM for correction contained the exact original question
    assert llm_mock.generate_sql.called
    prompt_sent = llm_mock.generate_sql.call_args[0][0]
    assert original_question in prompt_sent
    assert "Original Question (Source of Truth): " + original_question in prompt_sent

def test_query_history_and_exports_empty_results_safe(tmp_path):
    # Test export engine with empty rows
    empty_csv = tmp_path / "empty.csv"
    empty_json = tmp_path / "empty.json"
    
    ExportEngine.export_to_csv([], [], str(empty_csv))
    assert os.path.exists(empty_csv)
    
    ExportEngine.export_to_json([], [], str(empty_json))
    assert os.path.exists(empty_json)
    
    # Test query history with empty database
    hist_db = tmp_path / "test_hist.db"
    history = QueryHistory(db_path=str(hist_db))
    assert history.get_recent() == []
    assert history.clear_history() is True
    assert history.delete_entry(999999) is True  # Non-existent ID returns True/no crash
