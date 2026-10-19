"""
tests/test_byok.py - Verification of Bring Your Own Key (BYOK) AI Configuration
"""

import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_manager import session_manager
import backend.config as b_config


@pytest.fixture
def client():
    return TestClient(app)


def test_get_settings_default(client):
    """Verify that default settings return supported providers, models, and no raw secrets."""
    res_sess = client.post("/api/v1/auth/session")
    token = res_sess.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/settings/ai-provider", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "model" in data
    assert "supported_providers" in data
    assert len(data["supported_providers"]) >= 1

    groq_prov = next(p for p in data["supported_providers"] if p["id"] == "groq")
    assert len(groq_prov["models"]) >= 3
    # Ensure no raw API keys are leaked in response
    assert data["has_key"] is False
    assert data["masked_key"] is None


def test_save_valid_user_key(client):
    """Verify saving a user's API key updates the session in-memory and returns a masked key."""
    res_sess = client.post("/api/v1/auth/session")
    token = res_sess.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    secret_key = "gsk_test_secret_key_1234567890abcdef"
    save_payload = {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": secret_key
    }

    res_save = client.post("/api/v1/settings/ai-provider", headers=headers, json=save_payload)
    assert res_save.status_code == 200
    save_data = res_save.json()
    assert save_data["status"] == "success"
    assert save_data["has_key"] is True
    assert save_data["masked_key"].startswith("gsk_")
    assert save_data["masked_key"].endswith("cdef")
    # Verify the full secret is NOT returned in response
    assert secret_key not in str(save_data)

    # Check GET confirms key presence
    res_get = client.get("/api/v1/settings/ai-provider", headers=headers)
    get_data = res_get.json()
    assert get_data["has_key"] is True
    assert get_data["masked_key"] == save_data["masked_key"]
    assert secret_key not in str(get_data)


def test_settings_session_isolation(client):
    """
    Verify that Session A's key is strictly isolated from Session B.
    Modifying or deleting Session A's key has zero effect on Session B.
    """
    # Create Session A
    token_a = client.post("/api/v1/auth/session").json()["session_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create Session B
    token_b = client.post("/api/v1/auth/session").json()["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Save distinct keys
    key_a = "gsk_SESSION_ALPHA_KEY_99991111"
    key_b = "gsk_SESSION_BETA_KEY_88882222"

    client.post("/api/v1/settings/ai-provider", headers=headers_a, json={
        "provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": key_a
    })
    client.post("/api/v1/settings/ai-provider", headers=headers_b, json={
        "provider": "groq", "model": "llama-3.1-8b-instant", "api_key": key_b
    })

    # Verify Session A
    data_a = client.get("/api/v1/settings/ai-provider", headers=headers_a).json()
    assert data_a["model"] == "llama-3.3-70b-versatile"
    assert "1111" in data_a["masked_key"]
    assert "2222" not in data_a["masked_key"]

    # Verify Session B
    data_b = client.get("/api/v1/settings/ai-provider", headers=headers_b).json()
    assert data_b["model"] == "llama-3.1-8b-instant"
    assert "2222" in data_b["masked_key"]
    assert "1111" not in data_b["masked_key"]

    # Delete Session A's key
    client.delete("/api/v1/settings/ai-provider", headers=headers_a)
    assert client.get("/api/v1/settings/ai-provider", headers=headers_a).json()["has_key"] is False

    # Verify Session B is completely unaffected
    assert client.get("/api/v1/settings/ai-provider", headers=headers_b).json()["has_key"] is True


def test_missing_key_blocked_when_server_key_disabled(client, monkeypatch):
    """
    When ALLOW_SERVER_ENV_KEY is False (production default), queries without a user key
    must be rejected with a clear BYOK setup instruction and never use a server key.
    """
    monkeypatch.setattr(b_config, "ALLOW_SERVER_ENV_KEY", False)
    # Also patch query.py's imported reference
    from backend.routers import query
    monkeypatch.setattr(query, "ALLOW_SERVER_ENV_KEY", False)

    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload test CSV
    csv_bytes = b"product,sales\nWidget,100"
    client.post("/api/v1/upload", headers=headers, files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")})

    # Run query without configuring a key
    res = client.post("/api/v1/query", headers=headers, json={"question": "Show all sales"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ERROR"
    assert "AI Provider API key required" in data["error_message"]
    assert "Settings" in data["error_message"]


def test_remove_key_clears_session_memory(client):
    """Verify that DELETE /settings/ai-provider completely removes the key from the session."""
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": "gsk_test_key_to_delete_12345"
    })
    assert client.get("/api/v1/settings/ai-provider", headers=headers).json()["has_key"] is True

    # Remove key
    res_del = client.delete("/api/v1/settings/ai-provider", headers=headers)
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # Verify it is gone
    data_after = client.get("/api/v1/settings/ai-provider", headers=headers).json()
    assert data_after["has_key"] is False
    assert data_after["masked_key"] is None


def test_invalid_provider_or_model_rejected(client):
    """Verify input validation rejects invalid providers, unknown models, or malformed keys."""
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Invalid provider
    res_bad_prov = client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "unknown_ai", "model": "llama-3.3-70b-versatile", "api_key": "gsk_valid_length_key_12345"
    })
    assert res_bad_prov.status_code == 400

    # Invalid model
    res_bad_model = client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq", "model": "gpt-99-turbo", "api_key": "gsk_valid_length_key_12345"
    })
    assert res_bad_model.status_code == 400

    # Key too short
    res_short_key = client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": "short"
    })
    assert res_short_key.status_code == 422 or res_short_key.status_code == 400


def test_test_connection_endpoint_success(client, monkeypatch):
    """Verify test-connection endpoint returns success when Groq responds 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/settings/ai-provider/test", headers=headers, json={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": "gsk_test_mock_valid_key_12345"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "successful" in data["message"].lower()


def test_test_connection_endpoint_auth_failure(client, monkeypatch):
    """Verify test-connection endpoint safely reports 401 Unauthorized without exposing secret."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    secret = "gsk_test_unauthorized_key_99999"
    res = client.post("/api/v1/settings/ai-provider/test", headers=headers, json={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": secret
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "invalid api key" in data["message"].lower()
    # The actual secret must NOT appear in message
    assert secret not in str(data)


def test_secrets_never_appear_in_logs_or_errors(client):
    """Verify that SecretScrubbingFormatter redacts any user API keys from logs."""
    from logger import SecretScrubbingFormatter
    import logging

    secret_key = "gsk_VERY_SECRET_USER_KEY_88887777"
    formatter = SecretScrubbingFormatter('%(message)s')
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg=f"Error connecting with key {secret_key} to endpoint",
        args=(), exc_info=None
    )

    formatted = formatter.format(record)
    assert secret_key not in formatted
    assert "***REDACTED***" in formatted


def test_client_js_never_persists_raw_key_to_local_storage():
    """Audit: Verify that frontend JS code never saves raw API keys to localStorage or sessionStorage."""
    import re
    from pathlib import Path

    frontend_dir = Path("frontend/js")
    for js_file in frontend_dir.glob("*.js"):
        content = js_file.read_text(encoding="utf-8")
        # Ensure neither localStorage nor sessionStorage sets any AI API key
        assert not re.search(r'localStorage\.setItem\(.*(?:api_?key|user_key|groq)', content, re.IGNORECASE), (
            f"Found potential localStorage key persistence in {js_file.name}"
        )
        assert not re.search(r'sessionStorage\.setItem\(.*(?:api_?key|user_key|groq)', content, re.IGNORECASE), (
            f"Found potential sessionStorage key persistence in {js_file.name}"
        )


def test_production_blocks_server_env_key_even_when_groq_api_key_is_set(client, monkeypatch):
    """
    Audit: Verify that in production (ALLOW_SERVER_ENV_KEY = False), even if GROQ_API_KEY
    is set in the server environment, a user without their own BYOK key is blocked.
    """
    from backend.routers import query
    monkeypatch.setattr(b_config, "ALLOW_SERVER_ENV_KEY", False)
    monkeypatch.setattr(query, "ALLOW_SERVER_ENV_KEY", False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_server_shared_env_key_12345")

    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv_bytes = b"id,val\n1,10"
    client.post("/api/v1/upload", headers=headers, files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")})

    res = client.post("/api/v1/query", headers=headers, json={"question": "Show top rows"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ERROR"
    assert "AI Provider API key required" in data["error_message"]
    # Verify server key was not used or leaked
    assert "gsk_server_shared_env_key_12345" not in str(data)


def test_get_settings_schema_guarantees_no_raw_key(client):
    """Audit: Verify that GET /api/v1/settings/ai-provider schema never includes the raw API key."""
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    raw_key = "gsk_SUPER_CONFIDENTIAL_KEY_9876543210"
    client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq", "model": "llama-3.3-70b-versatile", "api_key": raw_key
    })

    res = client.get("/api/v1/settings/ai-provider", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "api_key" not in data
    assert raw_key not in str(data)
    assert data["has_key"] is True
    assert data["masked_key"] == "gsk_••••••••3210"


def test_error_formatting_redacts_registered_session_keys():
    """Audit: Verify that _format_ai_error redacts any session key from exception messages."""
    from backend.routers.query import _format_ai_error
    from logger import register_secret_to_scrub

    secret = "gsk_TEST_SECRET_EXCEPTION_KEY_112233"
    register_secret_to_scrub(secret)

    err = Exception(f"Internal provider exception containing {secret} in traceback")
    formatted = _format_ai_error(err)
    assert secret not in formatted
    assert "***REDACTED***" in formatted


def test_default_model_is_verified_gpt_oss_20b(client):
    """Verify that default settings return openai/gpt-oss-20b as the canonical recommended model."""
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/settings/ai-provider", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "openai/gpt-oss-20b"
    groq_prov = next(p for p in data["supported_providers"] if p["id"] == "groq")
    assert groq_prov["default_model"] == "openai/gpt-oss-20b"
    model_ids = [m["id"] for m in groq_prov["models"]]
    assert "openai/gpt-oss-20b" in model_ids
    assert "openai/gpt-oss-120b" in model_ids
    assert "qwen/qwen3.8-27b" in model_ids


def test_connection_test_with_404_model_reports_actionable_error(client, monkeypatch):
    """Verify that when a model returns HTTP 404 from Groq, an actionable error is returned."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/v1/settings/ai-provider/test", headers=headers, json={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": "gsk_valid_length_key_12345"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "Model 'llama-3.3-70b-versatile' not found on provider" in data["message"]


def test_save_settings_allows_switching_model_without_reentering_key(client):
    """Verify that a user with an active key can switch models without re-entering the key."""
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    secret_key = "gsk_initial_secret_key_12345678"
    client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "api_key": secret_key
    })

    # Switch model to openai/gpt-oss-120b without supplying api_key
    res_update = client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq",
        "model": "openai/gpt-oss-120b"
    })
    assert res_update.status_code == 200
    update_data = res_update.json()
    assert update_data["model"] == "openai/gpt-oss-120b"
    assert update_data["has_key"] is True
    assert update_data["masked_key"].endswith("5678")

    # Confirm via GET
    get_data = client.get("/api/v1/settings/ai-provider", headers=headers).json()
    assert get_data["model"] == "openai/gpt-oss-120b"
    assert get_data["has_key"] is True


def test_save_settings_validation_failure_preserves_existing_key(client, monkeypatch):
    """
    Verify that if Save & Apply runs with validate_connection=True and provider rejects
    the model (404), the session's existing key and model are preserved.
    """
    token = client.post("/api/v1/auth/session").json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    secret_key = "gsk_valid_working_key_99990000"
    # Initial successful save
    client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "api_key": secret_key
    })

    # Mock provider returning 404 for an unavailable model
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: mock_resp)

    # Attempt to switch to an unavailable model with validate_connection=True
    res_bad = client.post("/api/v1/settings/ai-provider", headers=headers, json={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "validate_connection": True
    })
    assert res_bad.status_code == 400
    assert "not found on provider" in res_bad.json()["detail"]

    # Verify existing session model and key remain completely intact
    get_data = client.get("/api/v1/settings/ai-provider", headers=headers).json()
    assert get_data["model"] == "openai/gpt-oss-20b"
    assert get_data["has_key"] is True
    assert get_data["masked_key"].endswith("0000")
