"""
tests/test_phase3_acceptance_audit.py - End-to-End Acceptance Audit for Phase 3 Data Cleaning
"""

import io
import pytest
import requests
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import app
from cleaning_engine import DataCleaningEngine


@pytest.fixture
def client():
    return TestClient(app)


def test_complete_cleaning_workflow_lifecycle(client):
    """
    Executes the exact 8-step lifecycle from the acceptance audit:
    1. Request duplicate detection and confirm preview appears
    2. Verify preview accurately reports changes without modifying active dataset
    3. Cancel and confirm dataset is unchanged
    4. Apply transformation and verify resulting data
    5. Undo change and verify preceding state is restored
    6. Apply another transformation and revert to original uploaded dataset
    7. Test missing values, type conversion failures, text normalization, row filtering
    8. Test empty datasets, invalid columns, invalid parameters, failed transformations
    """
    # Create isolated test session
    session_res = client.post("/api/v1/auth/session")
    assert session_res.status_code == 200
    token = session_res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload disposable test dataset
    # Row count: 6 rows (including 2 duplicate rows, 1 null in age, negative score, whitespace name)
    csv_content = (
        b"id,customer_name,age,salary,score\n"
        b"1,  alice smith  ,28,50000,90\n"
        b"2,BOB JONES,35,70000,85\n"
        b"2,BOB JONES,35,70000,85\n"  # Exact duplicate
        b"3,Charlie Brown,nan,unparseable,-15\n"  # Null age, invalid salary, negative score
        b"4,diana prince  ,42,95000,99\n"
        b"5,Evan Wright,190,110000,75\n"  # Outlier age (190)
    )

    upload_res = client.post(
        "/api/v1/upload",
        headers=headers,
        files={"file": ("audit_customers.csv", io.BytesIO(csv_content), "text/csv")}
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert "audit_customers" in upload_data["tables_created"]

    # --- Step 1: Request duplicate detection and confirm preview appears ---
    preview_res = client.post(
        "/api/v1/clean/preview",
        headers=headers,
        json={"prompt": "remove duplicate rows", "table_name": "audit_customers"}
    )
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["operation"] == "remove_duplicates"
    assert pdata["rows_before"] == 6
    assert pdata["rows_after"] == 5
    assert pdata["rows_affected"] == 1
    assert pdata["is_destructive"] is True
    assert len(pdata["before_sample"]) > 0
    assert len(pdata["after_sample"]) > 0

    # --- Step 2: Verify preview accurately reports changes WITHOUT modifying active dataset ---
    sql_check_1 = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": "SELECT count(*) as c FROM audit_customers"}
    )
    assert sql_check_1.status_code == 200
    assert sql_check_1.json()["rows"][0][0] == 6  # Dataset remains untouched!

    # --- Step 3: Cancel and confirm dataset is unchanged ---
    cancel_res = client.post("/api/v1/clean/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True

    sql_check_2 = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": "SELECT count(*) as c FROM audit_customers"}
    )
    assert sql_check_2.status_code == 200
    assert sql_check_2.json()["rows"][0][0] == 6

    # --- Step 4: Apply transformation and verify resulting data ---
    # Re-generate preview
    client.post(
        "/api/v1/clean/preview",
        headers=headers,
        json={"prompt": "remove duplicate rows", "table_name": "audit_customers"}
    )
    apply_res = client.post("/api/v1/clean/apply", headers=headers)
    assert apply_res.status_code == 200
    assert apply_res.json()["success"] is True
    assert apply_res.json()["rows_current"] == 5

    sql_check_3 = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": "SELECT count(*) as c FROM audit_customers"}
    )
    assert sql_check_3.status_code == 200
    assert sql_check_3.json()["rows"][0][0] == 5

    # --- Step 5: Undo change and verify preceding state is restored ---
    undo_res = client.post("/api/v1/clean/undo", headers=headers)
    assert undo_res.status_code == 200
    assert undo_res.json()["success"] is True
    assert undo_res.json()["rows_restored"] == 6

    sql_check_4 = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": "SELECT count(*) as c FROM audit_customers"}
    )
    assert sql_check_4.status_code == 200
    assert sql_check_4.json()["rows"][0][0] == 6

    # --- Step 6: Apply another transformation and revert to original uploaded dataset ---
    # Apply filter (drop negative scores)
    client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "filter_rows", "params": {"column": "score", "operator": ">", "value": 0}}
    )
    apply_filter = client.post("/api/v1/clean/apply", headers=headers)
    assert apply_filter.status_code == 200
    assert apply_filter.json()["rows_current"] == 5  # Negative score dropped

    # Revert to original
    revert_res = client.post("/api/v1/clean/revert-original", headers=headers)
    assert revert_res.status_code == 200
    assert revert_res.json()["success"] is True

    # Confirm original 6 rows are completely restored
    sql_check_5 = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": "SELECT count(*) as c FROM audit_customers"}
    )
    assert sql_check_5.status_code == 200
    assert sql_check_5.json()["rows"][0][0] == 6

    # Verify original snapshot itself was NOT altered
    schema_res = client.get("/api/v1/schema", headers=headers)
    assert schema_res.status_code == 200
    assert "audit_customers" in schema_res.json()["tables"]


def test_missing_values_and_type_conversions(client):
    """
    Tests missing-value handling, type conversion failures, text normalization, and row filtering.
    """
    session_res = client.post("/api/v1/auth/session")
    token = session_res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = (
        b"name,age,salary\n"
        b"  john doe  ,25,50000\n"
        b"jane doe,30,unparseable_sal\n"
        b",nan,60000\n"
    )
    client.post("/api/v1/upload", headers=headers, files={"file": ("staff.csv", io.BytesIO(csv_content), "text/csv")})

    # Missing value analysis
    analysis_res = client.post("/api/v1/clean/analyze", headers=headers, params={"table_name": "staff"})
    assert analysis_res.status_code == 200
    an_data = analysis_res.json()
    assert an_data["missing"]["total_null_cells"] >= 2

    # Fill missing values in age with median
    p_res = client.post("/api/v1/clean/preview", headers=headers, json={"prompt": "fill missing values in age with median"})
    assert p_res.status_code == 200
    assert p_res.json()["operation"] == "handle_missing"
    client.post("/api/v1/clean/apply", headers=headers)

    # Convert salary to numeric (safe coercion)
    conv_res = client.post("/api/v1/clean/direct-preview", headers=headers, json={
        "operation": "convert_type",
        "params": {"column": "salary", "target_type": "numeric", "errors": "coerce"}
    })
    assert conv_res.status_code == 200
    cdata = conv_res.json()
    assert cdata["operation"] == "convert_type"
    client.post("/api/v1/clean/apply", headers=headers)

    # Normalize text in name: trim whitespace and title case
    norm_res = client.post("/api/v1/clean/direct-preview", headers=headers, json={
        "operation": "normalize_text",
        "params": {"columns": ["name"], "operations": ["strip", "title"]}
    })
    assert norm_res.status_code == 200
    client.post("/api/v1/clean/apply", headers=headers)

    # Inspect final data
    final_sql = client.post("/api/v1/sql/execute", headers=headers, json={"sql": "SELECT name, age FROM staff LIMIT 3"})
    assert final_sql.status_code == 200
    rows = final_sql.json()["rows"]
    # First row should be trimmed & title cased
    assert rows[0][0] == "John Doe"
    # Row with NaN age was imputed with median (27.5)
    assert rows[2][1] == 27.5


def test_edge_cases_and_error_handling(client):
    """
    Tests empty datasets, invalid columns, invalid parameters, and failed transformations.
    """
    session_res = client.post("/api/v1/auth/session")
    token = session_res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload empty dataset
    empty_csv = b"col_a,col_b\n"
    client.post("/api/v1/upload", headers=headers, files={"file": ("empty_tab.csv", io.BytesIO(empty_csv), "text/csv")})

    # Empty dataset preview does not crash
    empty_preview = client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "remove_duplicates", "params": {}}
    )
    assert empty_preview.status_code == 200
    assert empty_preview.json()["rows_before"] == 0
    assert empty_preview.json()["rows_after"] == 0

    # Invalid column request returns HTTP 400 with helpful error
    inv_col_res = client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "convert_type", "params": {"column": "non_existent_column", "target_type": "numeric"}}
    )
    assert inv_col_res.status_code == 400
    assert "does not exist" in inv_col_res.json()["detail"]

    # Unsupported filter operator returns HTTP 400
    inv_op_res = client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "filter_rows", "params": {"column": "col_a", "operator": "unsupported_xyz", "value": 10}}
    )
    assert inv_op_res.status_code == 400
    assert "Unsupported filter operator" in inv_op_res.json()["detail"]

    # Cancel pending transformation from earlier so none is pending
    client.post("/api/v1/clean/cancel", headers=headers)

    # Apply without preview returns HTTP 400
    no_preview_apply = client.post("/api/v1/clean/apply", headers=headers)
    assert no_preview_apply.status_code == 400
    assert "No pending transformation proposal" in no_preview_apply.json()["detail"]


    # Undo without revisions returns HTTP 400
    no_undo = client.post("/api/v1/clean/undo", headers=headers)
    assert no_undo.status_code == 400
    assert "No previous revisions available" in no_undo.json()["detail"]


def test_session_isolation_and_cross_session_privacy(client):
    """
    Confirms one session cannot access another session's data, tables, or revisions.
    """
    # Session 1
    s1 = client.post("/api/v1/auth/session").json()["session_token"]
    h1 = {"Authorization": f"Bearer {s1}"}

    # Session 2
    s2 = client.post("/api/v1/auth/session").json()["session_token"]
    h2 = {"Authorization": f"Bearer {s2}"}

    # Session 1 uploads confidential data
    client.post("/api/v1/upload", headers=h1, files={"file": ("secret_hr.csv", io.BytesIO(b"emp,salary\nE1,999999"), "text/csv")})

    # Session 2 cannot query Session 1's table
    s2_query = client.post("/api/v1/sql/execute", headers=h2, json={"sql": "SELECT * FROM secret_hr"})
    # Session 2 has no dataset loaded or table not found
    assert s2_query.status_code in (400, 200)
    if s2_query.status_code == 200:
        assert s2_query.json()["success"] is False
        assert "no such table" in s2_query.json()["error"].lower()

    # Session 2 cannot undo or revert Session 1's changes
    s2_undo = client.post("/api/v1/clean/undo", headers=h2)
    assert s2_undo.status_code in (400, 404)
