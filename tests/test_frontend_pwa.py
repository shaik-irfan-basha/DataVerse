"""
tests/test_frontend_pwa.py - Verification of Static Frontend Serving and PWA Assets
"""

import pytest
from fastapi.testclient import TestClient
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root_serves_html_for_browser(client):
    """When a browser requests '/', text/html should be served containing the app shell."""
    res = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "DataVerse" in res.text
    assert '<div id="app-container">' in res.text
    assert '<script type="module" src="/js/app.js">' in res.text


def test_root_serves_json_for_api_clients(client):
    """When an API client or test requests '/', metadata JSON should be served."""
    res = client.get("/", headers={"Accept": "application/json"})
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    assert data["docs_url"] == "/docs"
    assert data["service"] == "DataVerse Intelligence Platform API"


def test_pwa_manifest_served(client):
    """Verify that /manifest.json is served with valid JSON and correct PWA fields."""
    res = client.get("/manifest.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "DataVerse"
    assert data["short_name"] == "DataVerse"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 2


def test_service_worker_served(client):
    """Verify that /sw.js is served with JavaScript MIME type and contains cache bypass."""
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert "dataverse-shell" in res.text
    assert "BYPASS CACHE FOR ALL API CALLS" in res.text


def test_css_stylesheets_served(client):
    """Verify that CSS stylesheets are served with text/css content type."""
    res_style = client.get("/css/style.css")
    assert res_style.status_code == 200
    assert "text/css" in res_style.headers["content-type"]
    assert "--bg-app" in res_style.text

    res_comp = client.get("/css/components.css")
    assert res_comp.status_code == 200
    assert "text/css" in res_comp.headers["content-type"]
    assert ".btn-primary" in res_comp.text


def test_javascript_modules_served(client):
    """Verify that ES modules (app.js, api.js, state.js, ui.js) are properly served."""
    for mod in ["app.js", "api.js", "state.js", "ui.js"]:
        res = client.get(f"/js/{mod}")
        assert res.status_code == 200
        assert "javascript" in res.headers["content-type"]


def test_pwa_icons_served(client):
    """Verify that the favicon and PWA app icons are served correctly."""
    res_svg = client.get("/icons/favicon.svg")
    assert res_svg.status_code == 200
    assert "image/svg+xml" in res_svg.headers["content-type"]

    res_192 = client.get("/icons/icon-192.png")
    assert res_192.status_code == 200
    assert "image/png" in res_192.headers["content-type"]

    res_512 = client.get("/icons/icon-512.png")
    assert res_512.status_code == 200
    assert "image/png" in res_512.headers["content-type"]


def test_api_routes_not_masked_by_static_mount(client):
    """Ensure that API routes under /api/v1 are not shadowed or masked by StaticFiles."""
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    res_auth = client.post("/api/v1/auth/session")
    assert res_auth.status_code == 200
    assert "session_token" in res_auth.json()


def test_frontend_clarification_contract_in_js_modules(client):
    """
    Ensure the frontend JS modules implement the required clarification contract:
    - api.js enforces and sends original_question, clarification_question, user_response
    - state.js preserves original_question in setQueryClarification and setQueryStarting
    - app.js extracts and passes originalQuestion to submitClarification
    """
    api_js = client.get("/js/api.js").text
    assert "original_question: cleanOriginal" in api_js
    assert "clarification_question: cleanClarification" in api_js
    assert "user_response: cleanResponse" in api_js

    state_js = client.get("/js/state.js").text
    assert "setQueryStarting" in state_js
    assert "original_question: original" in state_js

    app_js = client.get("/js/app.js").text
    assert "api.submitClarification" in app_js
    assert "originalQuestion" in app_js
