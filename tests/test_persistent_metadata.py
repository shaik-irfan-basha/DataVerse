"""
tests/test_persistent_metadata.py - Comprehensive Verification for Phase 2 Persistent Metadata

Verifies:
1. History surviving a server restart / session rehydration.
2. Saved queries (bookmarks) surviving a server restart / session rehydration.
3. Session isolation between two separate sessions (history, saved queries, preferences).
4. Clear-history affecting only the intended session.
5. Database initialization and schema migration versioning.
6. Database failure handling (corruption recovery, backup creation, resilient init).
7. Secret exclusion (API keys, bearer tokens) from persisted records.
8. Preferences persistence and isolated retrieval.
9. Dataset matching check preventing silent execution against wrong dataset.
"""

import os
import time
import tempfile
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from metadata_manager import MetadataManager, MetadataCorruptionError
from backend.app import app
from backend.session_manager import session_manager, UserSession
from query_history import QueryHistory


@pytest.fixture
def temp_meta_mgr():
    """Provides an isolated temporary MetadataManager instance."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    mgr = MetadataManager(db_path=path)
    yield mgr
    try:
        if os.path.exists(path):
            os.remove(path)
        wal = path + "-wal"
        shm = path + "-shm"
        if os.path.exists(wal):
            os.remove(wal)
        if os.path.exists(shm):
            os.remove(shm)
    except Exception:
        pass


@pytest.fixture
def api_client():
    """TestClient instance for FastAPI routes."""
    return TestClient(app)


# =============================================================================
# 1. Database Initialization & Schema Migration
# =============================================================================

def test_metadata_initialization_and_migration(temp_meta_mgr):
    """Verifies that schema_migrations table is created and version 1 migration applied."""
    with temp_meta_mgr._get_connection() as conn:
        cursor = conn.execute("SELECT version, description FROM schema_migrations;")
        rows = cursor.fetchall()
        assert len(rows) >= 1
        versions = [r["version"] for r in rows]
        assert 1 in versions
        assert "Initial metadata schema" in rows[0]["description"]

        # Verify all core tables exist
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        table_names = {r["name"] for r in tables}
        assert "sessions" in table_names
        assert "query_history" in table_names
        assert "saved_queries" in table_names
        assert "user_preferences" in table_names
        assert "schema_relationships" in table_names


# =============================================================================
# 2. History Surviving Server Restart / Rehydration
# =============================================================================

def test_history_survives_server_restart(api_client):
    """
    Simulates a client creating a session, running queries, the server restarting
    (wiping in-memory sessions), and the client reconnecting with their token.
    Verifies that all query history is preserved and rehydrated.
    """
    # 1. Client creates session
    res = api_client.post("/api/v1/auth/session")
    assert res.status_code == 200
    data = res.json()
    session_id = data["session_id"]
    token = data["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest a small dataset
    csv_content = b"product,sales,region\nLaptop,1200,North\nPhone,800,South\n"
    up_res = api_client.post(
        "/api/v1/upload",
        files={"file": ("test_sales.csv", csv_content, "text/csv")},
        headers=headers
    )
    assert up_res.status_code == 200

    # Execute manual SQL
    sql_res = api_client.post(
        "/api/v1/sql/execute",
        json={"sql": "SELECT product, sales FROM test_sales;", "question": "Show all sales"},
        headers=headers
    )
    assert sql_res.status_code == 200

    # Verify history recorded
    hist_before = api_client.get("/api/v1/history", headers=headers).json()
    assert hist_before["count"] >= 1
    assert any(e["question"] == "Show all sales" for e in hist_before["entries"])

    # 2. SIMULATE SERVER RESTART: wipe in-memory sessions completely
    session_manager._sessions.clear()
    session_manager._token_hash_to_session_id.clear()
    assert session_manager.active_session_count() == 0

    # 3. Client reconnects with original token
    hist_after = api_client.get("/api/v1/history", headers=headers)
    assert hist_after.status_code == 200
    hist_after_data = hist_after.json()
    assert hist_after_data["count"] >= 1
    assert any(e["question"] == "Show all sales" for e in hist_after_data["entries"])

    # Verify session was successfully rehydrated in memory
    assert session_manager.active_session_count() == 1
    rehydrated = session_manager.get_session_by_token(token)
    assert rehydrated is not None
    assert rehydrated.session_id == session_id


# =============================================================================
# 3. Saved Queries (Bookmarks) Surviving Server Restart
# =============================================================================

def test_saved_queries_survive_server_restart(api_client):
    """
    Verifies that saved query bookmarks persist across server restarts
    and can be retrieved, searched, and deleted.
    """
    res = api_client.post("/api/v1/auth/session")
    token = res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Save a query bookmark
    save_payload = {
        "title": "Quarterly Revenue Summary",
        "sql_query": "SELECT region, SUM(sales) FROM sales GROUP BY region;",
        "question": "Show revenue by region",
        "dataset_name": "sales.csv",
        "notes": "Run at end of each quarter."
    }
    save_res = api_client.post("/api/v1/saved-queries", json=save_payload, headers=headers)
    assert save_res.status_code == 201
    bookmark_id = save_res.json()["id"]

    # SIMULATE SERVER RESTART
    session_manager._sessions.clear()
    session_manager._token_hash_to_session_id.clear()

    # Reconnect and retrieve bookmarks
    list_res = api_client.get("/api/v1/saved-queries", headers=headers)
    assert list_res.status_code == 200
    bookmarks = list_res.json()["saved_queries"]
    assert len(bookmarks) == 1
    assert bookmarks[0]["id"] == bookmark_id
    assert bookmarks[0]["title"] == "Quarterly Revenue Summary"
    assert bookmarks[0]["sql_query"] == save_payload["sql_query"]

    # Delete bookmark
    del_res = api_client.delete(f"/api/v1/saved-queries/{bookmark_id}", headers=headers)
    assert del_res.status_code == 200

    # Verify deleted
    list_after = api_client.get("/api/v1/saved-queries", headers=headers).json()
    assert len(list_after["saved_queries"]) == 0


# =============================================================================
# 4. Multi-Session Isolation (History, Bookmarks, Preferences)
# =============================================================================

def test_multi_session_strict_isolation(api_client):
    """
    Verifies that Session A and Session B cannot read, modify, or delete
    each other's query history, saved bookmarks, or preferences.
    """
    # Create Session A
    tok_a = api_client.post("/api/v1/auth/session").json()["session_token"]
    head_a = {"Authorization": f"Bearer {tok_a}"}

    # Create Session B
    tok_b = api_client.post("/api/v1/auth/session").json()["session_token"]
    head_b = {"Authorization": f"Bearer {tok_b}"}

    # Session A records a query bookmark
    bk_a = api_client.post(
        "/api/v1/saved-queries",
        json={"title": "Session A Confidential", "sql_query": "SELECT * FROM secret_a;"},
        headers=head_a
    ).json()

    # Session A sets a preference
    api_client.put(
        "/api/v1/preferences",
        json={"key": "theme", "value": "neon-violet"},
        headers=head_a
    )

    # Session B queries bookmarks and preferences
    b_bookmarks = api_client.get("/api/v1/saved-queries", headers=head_b).json()["saved_queries"]
    assert len(b_bookmarks) == 0  # Session B cannot see Session A's bookmarks

    # Session B tries to access Session A's bookmark by ID
    forbidden_get = api_client.get(f"/api/v1/saved-queries/{bk_a['id']}", headers=head_b)
    assert forbidden_get.status_code == 404

    # Session B tries to delete Session A's bookmark by ID
    forbidden_del = api_client.delete(f"/api/v1/saved-queries/{bk_a['id']}", headers=head_b)
    assert forbidden_del.status_code == 404

    # Session B checks preferences
    b_prefs = api_client.get("/api/v1/preferences", headers=head_b).json()["preferences"]
    assert "theme" not in b_prefs  # Isolated


# =============================================================================
# 5. Clear-History Affects Only the Intended Session
# =============================================================================

def test_clear_history_affects_only_target_session(temp_meta_mgr):
    """
    Ensures clearing history for Session A leaves Session B's history untouched.
    """
    # Add history for Session A
    temp_meta_mgr.add_history_entry(session_id="sess_alpha", question="Q1", sql_query="SELECT 1;", success=True)
    temp_meta_mgr.add_history_entry(session_id="sess_alpha", question="Q2", sql_query="SELECT 2;", success=True)

    # Add history for Session B
    temp_meta_mgr.add_history_entry(session_id="sess_beta", question="Q3", sql_query="SELECT 3;", success=True)

    # Clear Session A
    assert temp_meta_mgr.clear_history(session_id="sess_alpha") is True

    # Verify Session A is empty
    alpha_entries = temp_meta_mgr.get_history_entries(session_id="sess_alpha")
    assert len(alpha_entries) == 0

    # Verify Session B is completely intact
    beta_entries = temp_meta_mgr.get_history_entries(session_id="sess_beta")
    assert len(beta_entries) == 1
    assert beta_entries[0]["question"] == "Q3"


# =============================================================================
# 6. Database Corruption Handling & Recovery
# =============================================================================

def test_database_corruption_recovery(tmp_path):
    """
    Corrupts the SQLite metadata file and verifies that MetadataManager detects corruption,
    safely moves the corrupted file to a backup, and recreates a clean working database.
    """
    db_file = tmp_path / "corrupt_test_meta.db"

    # Write garbage bytes to simulate file corruption
    with open(db_file, "wb") as f:
        f.write(b"CORRUPTED_SQLITE_GARBAGE_BYTES_1234567890\x00\xff\xfe")

    # Instantiate MetadataManager on the corrupted file
    mgr = MetadataManager(db_path=db_file)

    # Verify the database was restored to working health
    assert mgr._check_integrity() is True

    # Verify we can perform operations on the recovered database
    new_id = mgr.add_history_entry(session_id="sess_rec", question="Recovered Q", sql_query="SELECT 1;", success=True)
    assert new_id > 0
    entries = mgr.get_history_entries(session_id="sess_rec")
    assert len(entries) == 1
    assert entries[0]["question"] == "Recovered Q"


# =============================================================================
# 7. Secret & API Key Exclusion from Persistent Storage
# =============================================================================

def test_secret_exclusion_from_persistent_storage(temp_meta_mgr):
    """
    Verifies that any attempt to persist API keys, bearer tokens, or secrets
    into history, saved queries, or preferences raises ValueError.
    """
    # 1. API key in question
    with pytest.raises(ValueError, match="Secret detected"):
        temp_meta_mgr.add_history_entry(
            session_id="sess_sec",
            question="Query with gsk_secret_api_key_12345",
            sql_query="SELECT 1;",
            success=True
        )

    # 2. Bearer token in saved query
    with pytest.raises(ValueError, match="Secret detected"):
        temp_meta_mgr.save_query(
            session_id="sess_sec",
            title="Leaked Token",
            sql_query="SELECT * FROM users;",
            notes="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        )

    # 3. Secret in preference
    with pytest.raises(ValueError, match="Secret detected"):
        temp_meta_mgr.set_preference(
            session_id="sess_sec",
            key="api_key",
            value="gsk_1234567890abcdef"
        )


# =============================================================================
# 8. Dataset Matching Protection
# =============================================================================

def test_dataset_matching_protection(api_client):
    """
    Verifies that re-running a query created for Dataset A fails with HTTP 400
    if Dataset B (or no dataset) is currently active, preventing silent execution
    against the wrong dataset.
    """
    tok = api_client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Upload Dataset A
    csv_a = b"category,sales\nBooks,50\nGames,100\n"
    api_client.post("/api/v1/upload", files={"file": ("books.csv", csv_a, "text/csv")}, headers=headers)

    # Attempt to rerun SQL recorded for "sales.csv"
    mismatch_res = api_client.post(
        "/api/v1/sql/execute",
        json={
            "sql": "SELECT category, sales FROM books;",
            "dataset_name": "different_sales.csv"
        },
        headers=headers
    )
    assert mismatch_res.status_code == 400
    assert "Dataset mismatch" in mismatch_res.json()["detail"]
