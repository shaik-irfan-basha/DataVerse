"""
tests/test_session_isolation.py - Multi-Tenant Session Isolation & Privacy Verification
"""

import io
import time
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_manager import session_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_multi_session_database_isolation(client):
    """
    Verifies that two distinct sessions have completely isolated in-memory SQLite sandboxes.
    Session A cannot query, see, or access tables created by Session B, and vice-versa.
    """
    # 1. Create Session A
    res_a = client.post("/api/v1/auth/session")
    assert res_a.status_code == 200
    token_a = res_a.json()["session_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Create Session B
    res_b = client.post("/api/v1/auth/session")
    assert res_b.status_code == 200
    token_b = res_b.json()["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    assert token_a != token_b

    # 3. Session A uploads dataset A
    csv_a = b"account_id,balance\n101,95000\n102,120000"
    client.post(
        "/api/v1/upload",
        headers=headers_a,
        files={"file": ("alpha_bank.csv", io.BytesIO(csv_a), "text/csv")}
    )

    # 4. Session B uploads dataset B
    csv_b = b"patient_id,diagnosis\nP1,Confidential_X\nP2,Confidential_Y"
    client.post(
        "/api/v1/upload",
        headers=headers_b,
        files={"file": ("medical_records.csv", io.BytesIO(csv_b), "text/csv")}
    )

    # 5. Verify Schema Isolation
    schema_a = client.get("/api/v1/schema", headers=headers_a).json()
    schema_b = client.get("/api/v1/schema", headers=headers_b).json()

    assert "alpha_bank" in schema_a["tables"]
    assert "medical_records" not in schema_a["tables"]

    assert "medical_records" in schema_b["tables"]
    assert "alpha_bank" not in schema_b["tables"]

    # 6. Verify Execution Isolation: Session A attempts to query Session B's table
    attempt_a = client.post(
        "/api/v1/sql/execute",
        headers=headers_a,
        json={"sql": "SELECT * FROM medical_records;"}
    ).json()
    assert attempt_a["success"] is False
    assert "no such table: medical_records" in attempt_a["error"].lower()

    # 7. Verify Execution Isolation: Session B attempts to query Session A's table
    attempt_b = client.post(
        "/api/v1/sql/execute",
        headers=headers_b,
        json={"sql": "SELECT * FROM alpha_bank;"}
    ).json()
    assert attempt_b["success"] is False
    assert "no such table: alpha_bank" in attempt_b["error"].lower()


def test_cross_session_history_isolation(client):
    """
    Verifies that query history is strictly partitioned by session.
    """
    res_1 = client.post("/api/v1/auth/session").json()
    token_1 = res_1["session_token"]
    headers_1 = {"Authorization": f"Bearer {token_1}"}

    res_2 = client.post("/api/v1/auth/session").json()
    token_2 = res_2["session_token"]
    headers_2 = {"Authorization": f"Bearer {token_2}"}

    # Session 1 loads data and queries
    csv_data = b"id,val\n1,10"
    client.post("/api/v1/upload", headers=headers_1, files={"file": ("test.csv", io.BytesIO(csv_data), "text/csv")})
    client.post("/api/v1/sql/execute", headers=headers_1, json={"sql": "SELECT * FROM test;"})

    # Session 1 history should have at least 1 entry
    h1 = client.get("/api/v1/history", headers=headers_1).json()
    assert h1["count"] >= 1

    # Session 2 history must be empty (0 entries)
    h2 = client.get("/api/v1/history", headers=headers_2).json()
    assert h2["count"] == 0


def test_session_destruction_and_cleanup(client):
    """
    Verifies that destroying a session purges memory and removes the scratch directory.
    """
    res = client.post("/api/v1/auth/session").json()
    sid = res["session_id"]
    token = res["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session_obj = session_manager.get_session(sid)
    assert session_obj is not None
    temp_dir = session_obj.temp_dir
    assert temp_dir.exists()

    # Destroy session
    destroyed = session_manager.destroy_session(sid)
    assert destroyed is True

    # Token should now be invalid
    unauth_res = client.get("/api/v1/schema", headers=headers)
    assert unauth_res.status_code == 401

    # Temporary directory should be cleaned up
    assert not temp_dir.exists()


def test_session_ttl_expiration(client):
    """
    Verifies that sessions older than TTL are evicted and rejected.
    """
    res = client.post("/api/v1/auth/session").json()
    sid = res["session_id"]
    token = res["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session_obj = session_manager.get_session(sid)
    assert session_obj is not None

    # Artificially age the session past TTL (3600 seconds)
    session_obj.last_accessed = time.time() - 4000
    assert session_obj.is_expired(ttl_seconds=3600) is True

    # Next request with this token should fail with 401
    unauth_res = client.get("/api/v1/schema", headers=headers)
    assert unauth_res.status_code == 401
