"""
tests/test_api_endpoints.py - Comprehensive API Endpoint & Security Test Suite
"""

import io
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_manager import session_manager


@pytest.fixture
def client():
    # Use TestClient with base app
    return TestClient(app)


@pytest.fixture
def auth_session(client):
    """Creates a fresh authenticated session and returns (session_id, token, headers)."""
    res = client.post("/api/v1/auth/session")
    assert res.status_code == 200
    data = res.json()
    token = data["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return data["session_id"], token, headers


# =============================================================================
# 1. Health & System Tests
# =============================================================================

def test_health_endpoint(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "dataverse-api"
    assert "active_sessions" in data
    assert "llm_provider" in data


def test_root_welcome(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "docs_url" in data
    assert data["docs_url"] == "/docs"


# =============================================================================
# 2. Authentication & Authorization Guard Tests
# =============================================================================

def test_auth_session_creation(client):
    res = client.post("/api/v1/auth/session")
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "session_token" in data
    assert data["session_id"].startswith("sess_")
    assert data["expires_in"] > 0


def test_unauthorized_requests_rejected(client):
    # Calling protected endpoints without token must return 401
    assert client.get("/api/v1/schema").status_code == 401
    assert client.get("/api/v1/suggestions").status_code == 401
    assert client.get("/api/v1/history").status_code == 401
    assert client.post("/api/v1/query", json={"question": "Test"}).status_code == 401
    assert client.post("/api/v1/sql/execute", json={"sql": "SELECT 1"}).status_code == 401


def test_invalid_bearer_token_rejected(client):
    headers = {"Authorization": "Bearer bogus_token_value_xyz"}
    res = client.get("/api/v1/schema", headers=headers)
    assert res.status_code == 401
    assert "Invalid or expired session token" in res.json()["detail"]


def test_alternative_header_x_session_token(client):
    # Authenticate via X-Session-Token header
    session_res = client.post("/api/v1/auth/session").json()
    token = session_res["session_token"]

    headers = {"X-Session-Token": token}
    res = client.get("/api/v1/schema", headers=headers)
    assert res.status_code == 200


# =============================================================================
# 3. Dataset Ingestion, Validation & Schema Inspection
# =============================================================================

def test_dataset_upload_csv(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,name,role,salary\n1,Alice,Engineer,95000\n2,Bob,Captain,110000\n3,Charlie,Pilot,80000"
    files = {"file": ("crew_members.csv", io.BytesIO(csv_content), "text/csv")}

    res = client.post("/api/v1/upload", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    assert data["filename"] == "crew_members.csv"
    assert "crew_members" in data["tables_created"]
    assert "crew_members" in data["schema_overview"]
    assert len(data["suggested_questions"]) > 0


def test_dataset_upload_unsupported_format(client, auth_session):
    _, _, headers = auth_session
    files = {"file": ("malicious_script.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}

    res = client.post("/api/v1/upload", headers=headers, files=files)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_schema_inspection(client, auth_session):
    _, _, headers = auth_session

    # Before upload -> is_loaded = False
    res = client.get("/api/v1/schema", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_loaded"] is False

    # Upload data
    csv_content = b"id,item,price\n1,Widget,19.99\n2,Gadget,49.99"
    files = {"file": ("catalog.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    # After upload -> is_loaded = True with table details
    res_after = client.get("/api/v1/schema", headers=headers)
    assert res_after.status_code == 200
    data = res_after.json()
    assert data["is_loaded"] is True
    assert "catalog" in data["tables"]
    assert len(data["schema_overview"]["catalog"]) == 3


def test_suggestions_endpoint(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"department,budget,headcount\nSales,500000,25\nEngineering,1200000,40"
    files = {"file": ("org.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    res = client.get("/api/v1/suggestions", headers=headers)
    assert res.status_code == 200
    suggestions = res.json()["suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0


# =============================================================================
# 4. Manual SQL Execution & Security Authorizer Rejection Tests
# =============================================================================

def test_manual_sql_execution(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,name,score\n1,Alice,90\n2,Bob,85"
    files = {"file": ("students.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    payload = {"sql": "SELECT name, score FROM students WHERE score >= 90;"}
    res = client.post("/api/v1/sql/execute", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["row_count"] == 1
    assert data["columns"] == ["name", "score"]
    assert data["rows"] == [["Alice", 90]]


def test_destructive_sql_blocked_drop_table(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,val\n1,100"
    files = {"file": ("secure_data.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    # DROP TABLE must be blocked by authorizer / validator
    payload = {"sql": "DROP TABLE secure_data;"}
    res = client.post("/api/v1/sql/execute", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "UNAUTHORIZED_ACTION" in data["error"] or "Validation Failed" in data["error"]


def test_destructive_sql_blocked_delete(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,val\n1,100"
    files = {"file": ("secure_data2.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    payload = {"sql": "DELETE FROM secure_data2 WHERE id = 1;"}
    res = client.post("/api/v1/sql/execute", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False


def test_multi_statement_injection_blocked(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,val\n1,100"
    files = {"file": ("data_multi.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    payload = {"sql": "SELECT * FROM data_multi; DROP TABLE data_multi;"}
    res = client.post("/api/v1/sql/execute", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "Multiple SQL statements" in data["error"] or "MULTI_STATEMENT" in data["error"]


# =============================================================================
# 5. Table Profiling Tests
# =============================================================================

def test_table_profile_endpoint(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id,category,amount\n1,Food,15.5\n2,Travel,42.0\n3,Food,20.0"
    files = {"file": ("expenses.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    res = client.get("/api/v1/profile/expenses", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["table_name"] == "expenses"
    assert data["total_rows"] == 3
    assert data["total_columns"] == 3
    assert "amount" in [c["name"] for c in data["columns"]]


def test_table_profile_nonexistent(client, auth_session):
    _, _, headers = auth_session

    csv_content = b"id\n1"
    files = {"file": ("one.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    res = client.get("/api/v1/profile/nonexistent_table_xyz", headers=headers)
    assert res.status_code == 404


# =============================================================================
# 6. Chart Generation Tests
# =============================================================================

def test_chart_generation_endpoint(client, auth_session):
    _, _, headers = auth_session

    payload = {
        "columns": ["Department", "Budget"],
        "rows": [["Sales", 500000], ["Engineering", 1200000], ["Marketing", 300000]],
        "chart_type": "bar",
        "title": "Department Budgets"
    }

    res = client.post("/api/v1/chart", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["chart_type"] == "bar"
    assert data["base64_image"].startswith("data:image/png;base64,")
    assert "series_data" in data
    assert data["series_data"]["labels"] == ["Sales", "Engineering", "Marketing"]


def test_chart_empty_data_rejected(client, auth_session):
    _, _, headers = auth_session
    payload = {"columns": [], "rows": []}
    res = client.post("/api/v1/chart", headers=headers, json=payload)
    assert res.status_code == 400


# =============================================================================
# 7. Query History & Export Tests
# =============================================================================

def test_history_logging_and_clear(client, auth_session):
    _, _, headers = auth_session

    # Upload and execute a manual query
    csv_content = b"id\n1"
    files = {"file": ("h_data.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)
    client.post("/api/v1/sql/execute", headers=headers, json={"sql": "SELECT * FROM h_data;"})

    # Check history
    h_res = client.get("/api/v1/history", headers=headers)
    assert h_res.status_code == 200
    data = h_res.json()
    assert data["count"] >= 1

    # Clear history
    del_res = client.delete("/api/v1/history", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify history empty
    h_res_after = client.get("/api/v1/history", headers=headers)
    assert h_res_after.json()["count"] == 0


def test_export_endpoint(client, auth_session):
    _, _, headers = auth_session

    payload = {
        "format": "csv",
        "columns": ["Name", "Score"],
        "rows": [["Alice", 95], ["Bob", 88]],
        "filename": "custom_grades.csv"
    }

    res = client.post("/api/v1/export", headers=headers, json=payload)
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    assert "attachment; filename=\"custom_grades.csv\"" in res.headers.get("content-disposition", "")
    assert b"Alice,95" in res.content


# =============================================================================
# 8. Natural Language Query & Clarification Pipeline Tests
# =============================================================================

class StubLLM:
    def generate_json(self, prompt: str) -> dict:
        p_lower = prompt.lower()
        if "best" in p_lower and "by salary" not in p_lower:
            return {
                "is_ambiguous": True,
                "reasoning": "Subjective term 'best'",
                "clarification_question": "Do you mean by highest salary or experience?",
                "options": ["By Salary", "By Experience"]
            }
        return {
            "is_ambiguous": False,
            "reasoning": "Clear query",
            "sql_query": "SELECT name, salary FROM crew ORDER BY salary DESC LIMIT 1;"
        }

    def generate_sql(self, prompt: str) -> str:
        return "SELECT name, salary FROM crew ORDER BY salary DESC LIMIT 1;"


def test_nl_query_and_clarification_pipeline(client, auth_session):
    sid, _, headers = auth_session

    # 1. Upload crew dataset
    csv_content = b"id,name,salary\n1,Dallas,100000\n2,Ripley,120000\n3,Lambert,85000"
    files = {"file": ("crew.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    # Inject StubLLM into this session's query_service
    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = StubLLM()

    # 2. Ask an ambiguous question ("Who is our best crew member?")
    ambig_res = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "Who is our best crew member?"}
    )
    assert ambig_res.status_code == 200
    ambig_data = ambig_res.json()
    assert ambig_data["status"] == "CLARIFICATION_REQUIRED"
    assert "highest salary" in ambig_data["clarification_question"]
    assert "By Salary" in ambig_data["clarification_options"]
    assert ambig_data.get("original_question") == "Who is our best crew member?"

    # 3. Submit clarification answer via /api/v1/clarify
    clarify_payload = {
        "original_question": "Who is our best crew member?",
        "clarification_question": ambig_data["clarification_question"],
        "user_response": "By Salary"
    }
    resolved_res = client.post("/api/v1/clarify", headers=headers, json=clarify_payload)
    assert resolved_res.status_code == 200
    resolved_data = resolved_res.json()
    assert resolved_data["status"] == "SUCCESS"
    assert resolved_data.get("original_question") == "Who is our best crew member?"
    assert "SELECT name, salary FROM crew" in resolved_data["sql"]
    assert resolved_data["data"]["row_count"] == 1
    assert resolved_data["data"]["rows"][0] == ["Ripley", 120000]


def test_clarify_missing_original_question_reproduces_validation_failure(client, auth_session):
    """
    Regression test: Reproduce the exact 422 error observed in the frontend when
    original_question is omitted from the POST /api/v1/clarify payload.
    """
    sid, _, headers = auth_session
    csv_content = b"id,name\n1,Alpha"
    files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    # Missing original_question in payload
    invalid_payload = {
        "clarification_question": "Which column?",
        "user_response": "Just return the first 5 rows in the table, without sorting."
    }
    res = client.post("/api/v1/clarify", headers=headers, json=invalid_payload)
    assert res.status_code == 422
    err_detail = res.json()["detail"]
    assert any(
        err.get("loc") == ["body", "original_question"] and err.get("type") == "missing"
        for err in err_detail
    )


def test_clarify_with_valid_original_question_passes_validation(client, auth_session):
    """
    Regression test: Verify that including original_question satisfies ClarifyRequest
    and allows clarification submission to proceed.
    """
    class ClarifiedStubLLM:
        def generate_json(self, prompt: str) -> dict:
            p_lower = prompt.lower()
            if "without sorting" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "User specified no sorting",
                    "sql_query": "SELECT id, val FROM numbers LIMIT 5;"
                }
            return {
                "is_ambiguous": True,
                "reasoning": "Top requires ordering metric",
                "clarification_question": "Which column should be used to order the top rows?",
                "options": ["By val", "Without sorting"]
            }

        def generate_sql(self, prompt: str) -> str:
            return "SELECT id, val FROM numbers LIMIT 5;"

    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = ClarifiedStubLLM()

    # Valid payload containing original_question
    valid_payload = {
        "original_question": "Show the top 5 rows",
        "clarification_question": "Which column should be used to order the top rows?",
        "user_response": "Just return the first 5 rows in the table, without sorting."
    }
    res = client.post("/api/v1/clarify", headers=headers, json=valid_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["original_question"] == "Show the top 5 rows"
    assert "SELECT id, val FROM numbers LIMIT 5" in data["sql"]
    assert data["data"]["row_count"] == 3

    # Verify query history recorded original_question
    hist_res = client.get("/api/v1/history", headers=headers)
    assert hist_res.status_code == 200
    entries = hist_res.json()["entries"]
    assert len(entries) >= 1
    assert entries[0]["question"] == "Show the top 5 rows"
    assert "SELECT id, val FROM numbers LIMIT 5" in entries[0]["sql_query"]


def test_clarify_option_selection_controls_generated_sql(client, auth_session):
    """
    Regression test: Verify that user's selected clarification option
    directly determines the resulting SQL query and data output.
    """
    class OptionSelectiveStubLLM:
        def generate_json(self, prompt: str) -> dict:
            p_lower = prompt.lower()
            if "by value" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "Ordering by val descending",
                    "sql_query": "SELECT id, val FROM numbers ORDER BY val DESC LIMIT 5;"
                }
            elif "by id" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "Ordering by id ascending",
                    "sql_query": "SELECT id, val FROM numbers ORDER BY id ASC LIMIT 5;"
                }
            return {
                "is_ambiguous": True,
                "reasoning": "Ambiguous ordering metric",
                "clarification_question": "Which column to sort by?",
                "options": ["By value", "By id"]
            }

        def generate_sql(self, prompt: str) -> str:
            if "by value" in prompt.lower():
                return "SELECT id, val FROM numbers ORDER BY val DESC LIMIT 5;"
            return "SELECT id, val FROM numbers ORDER BY id ASC LIMIT 5;"

    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = OptionSelectiveStubLLM()

    # 1. Option A: 'By value'
    res_a = client.post("/api/v1/clarify", headers=headers, json={
        "original_question": "Show top rows",
        "clarification_question": "Which column to sort by?",
        "user_response": "By value"
    })
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["status"] == "SUCCESS"
    assert "ORDER BY val DESC" in data_a["sql"]
    assert data_a["data"]["rows"][0] == [3, 30]  # highest val first

    # 2. Option B: 'By id'
    res_b = client.post("/api/v1/clarify", headers=headers, json={
        "original_question": "Show top rows",
        "clarification_question": "Which column to sort by?",
        "user_response": "By id"
    })
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["status"] == "SUCCESS"
    assert "ORDER BY id ASC" in data_b["sql"]
    assert data_b["data"]["rows"][0] == [1, 10]  # lowest id first


def test_inpage_clarification_elements_rendered_in_frontend(client):
    """
    Regression test: Verify that index.html and components.css contain
    the in-page workspace clarification card, options, and SQL clarification badge.
    """
    html_res = client.get("/", headers={"Accept": "text/html"})
    assert html_res.status_code == 200
    html = html_res.text

    assert 'id="inpage-clarification-card"' in html
    assert 'id="inpage-clarification-question"' in html
    assert 'id="inpage-clarification-options"' in html
    assert 'id="inpage-custom-clarification-input"' in html
    assert 'id="inpage-clarification-reasoning"' in html
    assert 'id="inpage-clarification-edit-btn"' in html
    assert 'id="sql-clarification-tag"' in html
    assert 'Clarify your question' in html

    css_res = client.get("/css/components.css")
    assert css_res.status_code == 200
    css = css_res.text
    assert ".inpage-clarification-card" in css
    assert ".inpage-option-chip" in css
    assert ".inpage-clarification-actions" in css
    assert ".inpage-clarification-reasoning" in css


def test_clear_query_show_top_5_rows_direct_execution(client, auth_session):
    """
    Test: 'Show the top 5 rows' executes directly without unnecessary clarification.
    """
    class DirectExecutionStubLLM:
        def generate_json(self, prompt: str) -> dict:
            return {
                "is_ambiguous": False,
                "reasoning": "Clear row limit request",
                "sql_query": "SELECT id, val FROM numbers LIMIT 5;"
            }

        def generate_sql(self, prompt: str) -> str:
            return "SELECT id, val FROM numbers LIMIT 5;"

    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = DirectExecutionStubLLM()

    res = client.post("/api/v1/query", headers=headers, json={"question": "Show the top 5 rows"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "LIMIT 5" in data["sql"]
    assert data["data"]["row_count"] == 3


def test_ambiguous_query_returns_reasoning_and_options(client, auth_session):
    """
    Test: 'Show the best-performing products' returns CLARIFICATION_REQUIRED
    with clear reasoning, question, and selectable options.
    """
    class AmbiguousStubLLM:
        def generate_json(self, prompt: str) -> dict:
            return {
                "is_ambiguous": True,
                "reasoning": "Performance can be measured by total sales or average order value.",
                "clarification_question": "How should product performance be evaluated?",
                "options": ["Total Sales (SUM)", "Average Order Value (AVG)"]
            }

        def generate_sql(self, prompt: str) -> str:
            return ""

    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = AmbiguousStubLLM()

    res = client.post("/api/v1/query", headers=headers, json={"question": "Show the best-performing products"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert data["reasoning"] == "Performance can be measured by total sales or average order value."
    assert "How should product performance be evaluated?" in data["clarification_question"]
    assert len(data["clarification_options"]) == 2


def test_nonexistent_column_does_not_hallucinate(client, auth_session):
    """
    Test: A query referring to a nonexistent column explains that the column is missing
    and does not silently invent it.
    """
    class GroundedStubLLM:
        def generate_json(self, prompt: str) -> dict:
            return {
                "is_ambiguous": True,
                "reasoning": "Requested column 'salary' does not exist in schema.",
                "clarification_question": "The dataset does not contain 'salary'. Available columns are: id, val. How would you like to proceed?",
                "options": ["View id and val", "Total sum of val"]
            }

        def generate_sql(self, prompt: str) -> str:
            return ""

    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = GroundedStubLLM()

    res = client.post("/api/v1/query", headers=headers, json={"question": "What is the employee salary?"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert "salary" in data["reasoning"]
    assert "Available columns are: id, val" in data["clarification_question"]


def test_history_records_manual_sql_with_question_and_dataset_name(client, auth_session):
    """
    Test: Manual SQL execution records the prompt question, actual dataset filename,
    latency, row count, and SQL query into session history.
    """
    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10\n2,20\n3,30"
    files = {"file": ("numbers.csv", io.BytesIO(csv_content), "text/csv")}
    upload_res = client.post("/api/v1/upload", headers=headers, files=files)
    assert upload_res.status_code == 200

    sql_payload = {
        "sql": "SELECT id, val FROM numbers ORDER BY val DESC;",
        "question": "Show all numbers sorted by value descending"
    }
    sql_res = client.post("/api/v1/sql/execute", headers=headers, json=sql_payload)
    assert sql_res.status_code == 200
    assert sql_res.json()["success"] is True

    hist_res = client.get("/api/v1/history", headers=headers)
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["count"] >= 1
    entry = hist_data["entries"][0]
    assert entry["question"] == "Show all numbers sorted by value descending"
    assert "SELECT id, val FROM numbers" in entry["sql_query"]
    assert entry["dataset_name"] == "numbers.csv"
    assert entry["success"] is True
    assert entry["row_count"] == 3


def test_history_clearing_in_session(client, auth_session):
    """
    Test: DELETE /api/v1/history purges session query history completely.
    """
    sid, _, headers = auth_session
    csv_content = b"id,val\n1,10"
    files = {"file": ("items.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    client.post("/api/v1/sql/execute", headers=headers, json={"sql": "SELECT * FROM items;"})

    hist_before = client.get("/api/v1/history", headers=headers).json()
    assert hist_before["count"] >= 1

    del_res = client.delete("/api/v1/history", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    hist_after = client.get("/api/v1/history", headers=headers).json()
    assert hist_after["count"] == 0
    assert len(hist_after["entries"]) == 0


def test_history_ui_markup_presence(client):
    """
    Test: Ensure index.html includes search input, clear button, and filter pills.
    """
    res = client.get("/", headers={"Accept": "text/html"})
    assert res.status_code == 200
    html = res.text
    assert 'id="history-modal"' in html
    assert 'id="history-search-input"' in html
    assert 'id="btn-clear-history-search"' in html
    assert 'data-status-filter="all"' in html
    assert 'data-status-filter="success"' in html
    assert 'data-status-filter="failed"' in html


# =============================================================================
# 9. Clarification Engine Regression Tests (Intent Resolution & Entity Grounding)
# =============================================================================

def test_good_products_ambiguity_and_clarification_resolution(client, auth_session):
    """
    Regression test for User Request 10:
    Dataset: sample_sales.csv (product, sales, region)
    Query: 'Show me the good products.'
    Expected:
    1. Detects ambiguity ('good' has no defined metric/threshold).
    2. Does NOT hijack the goal with 'Sales by region' or execute prematurely.
    3. Returns product-grounded options (e.g., 'Highest sales by product', 'Lowest sales by product').
    4. Waits for user selection.
    5. Preserves original_question throughout clarification and SQL execution.
    6. Generates SQL strictly matching user's selected choice.
    """
    class GoodProductsStubLLM:
        def generate_json(self, prompt: str) -> dict:
            p_lower = prompt.lower()
            if "user: highest sales by product" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "User specified highest sales by product.",
                    "sql_query": "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales DESC;"
                }
            if "user: lowest sales by product" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "User specified lowest sales by product.",
                    "sql_query": "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales ASC;"
                }
            # Initial ambiguous question
            return {
                "is_ambiguous": True,
                "reasoning": "The qualitative term 'good' lacks a defined threshold or ranking metric in the schema.",
                "clarification_question": "How should good products be evaluated?",
                "options": [
                    "Highest sales by product",
                    "Lowest sales by product",
                    "Products ranked by sales descending",
                    "Products with sales above average"
                ]
            }

        def generate_sql(self, prompt: str) -> str:
            if "lowest sales" in prompt.lower():
                return "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales ASC;"
            return "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales DESC;"

    sid, _, headers = auth_session
    csv_content = b"product,sales,region\nLaptop,1200,North\nPhone,800,South\nTablet,400,East\nMonitor,300,West"
    files = {"file": ("sample_sales.csv", io.BytesIO(csv_content), "text/csv")}
    upload_res = client.post("/api/v1/upload", headers=headers, files=files)
    assert upload_res.status_code == 200

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = GoodProductsStubLLM()

    # Step 1: Submit ambiguous query "Show me the good products."
    q_res = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "Show me the good products."}
    )
    assert q_res.status_code == 200
    q_data = q_res.json()

    # Verify ambiguity detected and no premature execution
    assert q_data["status"] == "CLARIFICATION_REQUIRED"
    assert q_data["original_question"] == "Show me the good products."
    assert "good" in q_data["reasoning"].lower()
    assert q_data["clarification_question"] == "How should good products be evaluated?"
    assert len(q_data["clarification_options"]) == 4

    # Verify target entity grounding: all options must target products, NOT regions
    for opt in q_data["clarification_options"]:
        assert "product" in opt.lower()
        assert "region" not in opt.lower()
    assert q_data["data"] is None

    # Step 2: Choose Option 1: "Highest sales by product"
    clarify_res1 = client.post(
        "/api/v1/clarify",
        headers=headers,
        json={
            "original_question": "Show me the good products.",
            "clarification_question": q_data["clarification_question"],
            "user_response": "Highest sales by product"
        }
    )
    assert clarify_res1.status_code == 200
    res1_data = clarify_res1.json()
    assert res1_data["status"] == "SUCCESS"
    assert res1_data["original_question"] == "Show me the good products."
    assert "SELECT product" in res1_data["sql"]
    assert "ORDER BY total_sales DESC" in res1_data["sql"]
    assert res1_data["data"]["columns"] == ["product", "total_sales"]
    assert res1_data["data"]["rows"][0] == ["Laptop", 1200]

    # Step 3: Choose Option 2: "Lowest sales by product"
    clarify_res2 = client.post(
        "/api/v1/clarify",
        headers=headers,
        json={
            "original_question": "Show me the good products.",
            "clarification_question": q_data["clarification_question"],
            "user_response": "Lowest sales by product"
        }
    )
    assert clarify_res2.status_code == 200
    res2_data = clarify_res2.json()
    assert res2_data["status"] == "SUCCESS"
    assert res2_data["original_question"] == "Show me the good products."
    assert "SELECT product" in res2_data["sql"]
    assert "ORDER BY total_sales ASC" in res2_data["sql"]
    assert res2_data["data"]["columns"] == ["product", "total_sales"]
    assert res2_data["data"]["rows"][0] == ["Monitor", 300]


def test_important_sales_ambiguity_detection(client, auth_session):
    """
    Regression test: 'Show me the important sales' has undefined subjective importance
    and must return CLARIFICATION_REQUIRED with sales-grounded options.
    """
    class ImportantSalesStubLLM:
        def generate_json(self, prompt: str) -> dict:
            return {
                "is_ambiguous": True,
                "reasoning": "The qualitative term 'important' is subjective without a defined threshold in schema.",
                "clarification_question": "How should important sales be defined?",
                "options": [
                    "Transactions with highest sales",
                    "Sales above average transaction value",
                    "Total sales by product",
                    "Total sales by region"
                ]
            }

        def generate_sql(self, prompt: str) -> str:
            return ""

    sid, _, headers = auth_session
    csv_content = b"product,sales,region\nLaptop,1200,North\nPhone,800,South"
    files = {"file": ("sample_sales2.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = ImportantSalesStubLLM()

    res = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "Show me the important sales."}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert data["original_question"] == "Show me the important sales."
    assert "important" in data["reasoning"].lower()
    assert data["clarification_question"] == "How should important sales be defined?"
    assert len(data["clarification_options"]) >= 2
    assert data["data"] is None


def test_baseline_query_total_sales_by_region_direct_execution(client, auth_session):
    """
    Regression test: Baseline clear query 'What are total sales by region?'
    must execute directly without clarification.
    """
    class BaselineSalesByRegionStubLLM:
        def generate_json(self, prompt: str) -> dict:
            return {
                "is_ambiguous": False,
                "reasoning": "Direct aggregation and grouping of sales by region.",
                "sql_query": "SELECT region, SUM(sales) AS total_sales FROM sample_sales GROUP BY region ORDER BY total_sales DESC;"
            }

        def generate_sql(self, prompt: str) -> str:
            return "SELECT region, SUM(sales) AS total_sales FROM sample_sales GROUP BY region ORDER BY total_sales DESC;"

    sid, _, headers = auth_session
    csv_content = b"product,sales,region\nLaptop,1200,North\nPhone,800,South\nTablet,400,North"
    files = {"file": ("sample_sales.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = BaselineSalesByRegionStubLLM()

    res = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "What are total sales by region?"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["original_question"] == "What are total sales by region?"
    assert "SELECT region" in data["sql"]
    assert "SUM(sales)" in data["sql"]
    assert data["data"]["row_count"] == 2
    # Verify regional aggregations (North = 1600, South = 800)
    assert data["data"]["rows"][0] == ["North", 1600]
    assert data["data"]["rows"][1] == ["South", 800]


def test_stale_history_does_not_override_new_product_query(client, auth_session):
    """
    Regression test: Verify that if a previous query turn touched 'Sales by region',
    a new natural language query 'Show me the good products.' does not inherit
    that context or erroneously execute a regional sales aggregation.
    """
    class HistoryScopingStubLLM:
        def generate_json(self, prompt: str) -> dict:
            p_lower = prompt.lower()
            # If the engine correctly prioritizes the current question and ignores unrelated history:
            if "show me the good products" in p_lower and "user: highest sales by product" not in p_lower:
                return {
                    "is_ambiguous": True,
                    "reasoning": "The qualitative term 'good' lacks a defined threshold or ranking metric.",
                    "clarification_question": "How should good products be evaluated?",
                    "options": ["Highest sales by product", "Lowest sales by product"]
                }
            # If the user explicitly clarified this question:
            if "user: highest sales by product" in p_lower:
                return {
                    "is_ambiguous": False,
                    "reasoning": "User clarified by highest sales.",
                    "sql_query": "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales DESC;"
                }
            # Fallback
            return {
                "is_ambiguous": False,
                "reasoning": "Regional aggregation",
                "sql_query": "SELECT region, SUM(sales) AS total_sales FROM sample_sales GROUP BY region;"
            }

        def generate_sql(self, prompt: str) -> str:
            return "SELECT product, SUM(sales) AS total_sales FROM sample_sales GROUP BY product ORDER BY total_sales DESC;"

    sid, _, headers = auth_session
    csv_content = b"product,sales,region\nLaptop,1200,North\nPhone,800,South"
    files = {"file": ("sample_sales.csv", io.BytesIO(csv_content), "text/csv")}
    client.post("/api/v1/upload", headers=headers, files=files)

    session_obj = session_manager.get_session(sid)
    session_obj.query_service.llm_client = HistoryScopingStubLLM()

    # Send a new query with NO clarification history (clean top-level query)
    res = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "Show me the good products."}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert data["original_question"] == "Show me the good products."
    assert "product" in data["clarification_options"][0].lower()
    # It must NOT return regional sales
    assert "region" not in data.get("sql", "").lower()
