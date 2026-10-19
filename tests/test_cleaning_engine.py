"""
tests/test_cleaning_engine.py - Unit & Integration Tests for Conversational Data Cleaning

Validates:
1. Missing-value analysis and handling (drop rows/cols, fill mean/median/mode/constant/ffill/bfill)
2. Duplicate detection and deduplication (exact & subset)
3. Column type conversion with safe coercion and failed count tracking
4. Row filtering (operators: >, <, >=, <=, ==, !=, between, not_null, remove_negative, drop_outliers)
5. Basic text normalization with strict null preservation
6. Preview generation (before/after samples, affected counts, destructive detection)
7. Natural language intent parser
8. Session snapshots, revisions, undo, and revert to immutable original
9. Multi-tenant session isolation during data cleaning
10. Full API route integration (/api/v1/clean/* and conversational /query + /clarify)
"""

import io
import pytest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_manager import session_manager
from cleaning_engine import DataCleaningEngine


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_dirty_df():
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 5, 6],
        "name": [" Alice  ", "BOB", "Charlie!", "  david ", None, "david ", "Eve"],
        "age": [25.0, np.nan, 30.0, 45.0, 25.0, 25.0, 150.0],
        "salary": ["50000", "65000", "invalid", "80000", "50000", "50000", "70000"],
        "score": [-10, 85, 92, 78, 60, 60, 95]
    })


# =============================================================================
# 1. Missing Value Analysis & Handling Tests
# =============================================================================

def test_analyze_missing(sample_dirty_df):
    analysis = DataCleaningEngine.analyze_missing(sample_dirty_df)
    assert analysis["total_rows"] == 7
    assert analysis["total_columns"] == 5
    assert analysis["total_null_cells"] >= 2  # name has 1, age has 1
    assert "columns" in analysis

    age_col = next(c for c in analysis["columns"] if c["column"] == "age")
    assert age_col["null_count"] == 1
    assert age_col["is_numeric"] is True
    assert age_col["recommended_strategy"] == "fill_median"


def test_clean_missing_drop_rows(sample_dirty_df):
    cleaned, metrics = DataCleaningEngine.clean_missing(sample_dirty_df, strategy="drop_rows", columns=["age"])
    assert len(cleaned) == 6
    assert metrics["rows_affected"] == 1
    assert cleaned["age"].isnull().sum() == 0


def test_clean_missing_drop_columns(sample_dirty_df):
    cleaned, metrics = DataCleaningEngine.clean_missing(sample_dirty_df, strategy="drop_columns", columns=["age"])
    assert "age" not in cleaned.columns
    assert len(cleaned) == 7


def test_clean_missing_fill_numeric(sample_dirty_df):
    # Median
    cleaned_med, _ = DataCleaningEngine.clean_missing(sample_dirty_df, strategy="fill_median", columns=["age"])
    assert cleaned_med["age"].isnull().sum() == 0
    # Expected median of [25, 30, 45, 25, 25, 150] is 27.5
    assert cleaned_med.loc[1, "age"] == 27.5

    # Mean
    cleaned_mean, _ = DataCleaningEngine.clean_missing(sample_dirty_df, strategy="fill_mean", columns=["age"])
    assert cleaned_mean["age"].isnull().sum() == 0

    # Constant
    cleaned_const, _ = DataCleaningEngine.clean_missing(sample_dirty_df, strategy="fill_constant", columns=["age"], fill_value=99.0)
    assert cleaned_const.loc[1, "age"] == 99.0


def test_clean_missing_fill_mode_and_ffill():
    df = pd.DataFrame({"city": ["London", "Paris", None, "London", "Tokyo"]})
    cleaned_mode, _ = DataCleaningEngine.clean_missing(df, strategy="fill_mode", columns=["city"])
    assert cleaned_mode.loc[2, "city"] == "London"

    cleaned_ffill, _ = DataCleaningEngine.clean_missing(df, strategy="fill_forward", columns=["city"])
    assert cleaned_ffill.loc[2, "city"] == "Paris"


# =============================================================================
# 2. Duplicate Detection & Deduplication Tests
# =============================================================================

def test_analyze_and_clean_duplicates():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "name": ["A", "B", "B", "C"]
    })
    analysis = DataCleaningEngine.analyze_duplicates(df)
    assert analysis["duplicate_count"] == 1
    assert analysis["duplicate_percentage"] == 25.0

    cleaned, metrics = DataCleaningEngine.clean_duplicates(df, keep="first")
    assert len(cleaned) == 3
    assert metrics["rows_affected"] == 1


def test_clean_duplicates_subset():
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "val": [10, 20, 99, 40]
    })
    cleaned, metrics = DataCleaningEngine.clean_duplicates(df, subset=["id"], keep="last")
    assert len(cleaned) == 3
    assert cleaned.loc[cleaned["id"] == 2, "val"].values[0] == 99


# =============================================================================
# 3. Column Type Conversion Tests
# =============================================================================

def test_convert_type_numeric_safe_coercion():
    df = pd.DataFrame({"salary": ["1000", "2500.50", "N/A", "4000"]})
    cleaned, metrics = DataCleaningEngine.clean_convert_type(df, column="salary", target_type="numeric", errors="coerce")
    assert pd.api.types.is_float_dtype(cleaned["salary"])
    assert cleaned["salary"].isnull().sum() == 1  # 'N/A' became NaN
    assert metrics["failed_conversions"] == 1


def test_convert_type_integer_and_datetime():
    df = pd.DataFrame({
        "num": ["10", "20", "invalid", "40"],
        "date": ["2026-01-01", "2026-02-15", "bad-date", "2026-10-18"]
    })
    cleaned_int, _ = DataCleaningEngine.clean_convert_type(df, column="num", target_type="integer")
    assert str(cleaned_int["num"].dtype) == "Int64"
    assert cleaned_int["num"].isnull().sum() == 1

    cleaned_dt, _ = DataCleaningEngine.clean_convert_type(df, column="date", target_type="datetime")
    assert pd.api.types.is_datetime64_any_dtype(cleaned_dt["date"])
    assert cleaned_dt["date"].isnull().sum() == 1


# =============================================================================
# 4. Row Filtering Tests
# =============================================================================

def test_filter_rows_operators(sample_dirty_df):
    # Greater than
    cleaned, m = DataCleaningEngine.clean_filter_rows(sample_dirty_df, column="score", operator=">", value=0)
    assert len(cleaned) == 6
    assert (cleaned["score"] > 0).all()

    # Between
    cleaned_bt, _ = DataCleaningEngine.clean_filter_rows(sample_dirty_df, column="age", operator="between", min_val=20, max_val=40)
    assert len(cleaned_bt) == 4

    # Remove negative
    cleaned_pos, _ = DataCleaningEngine.clean_filter_rows(sample_dirty_df, column="score", operator="remove_negative")
    assert (cleaned_pos["score"] >= 0).all()

    # Outliers (IQR)
    cleaned_no_outlier, _ = DataCleaningEngine.clean_filter_rows(sample_dirty_df, column="age", operator="drop_outliers")
    assert 150.0 not in cleaned_no_outlier["age"].values


def test_filter_rows_100_percent_dropped_warning():
    df = pd.DataFrame({"val": [10, 20, 30]})
    cleaned, m = DataCleaningEngine.clean_filter_rows(df, column="val", operator=">", value=100)
    assert len(cleaned) == 0
    assert "Warning" in m.get("warning", "")


# =============================================================================
# 5. Basic Text Normalization Tests (with Null Preservation)
# =============================================================================

def test_normalize_text_null_preservation():
    df = pd.DataFrame({
        "name": ["  john doe  ", "JANE DOE", "mark@#$123", None]
    })
    cleaned, metrics = DataCleaningEngine.clean_normalize_text(
        df,
        columns=["name"],
        operations=["strip", "title", "remove_special"]
    )
    # Check null remains null and is NOT converted to string "None"
    assert pd.isnull(cleaned.loc[3, "name"])
    assert cleaned.loc[0, "name"] == "John Doe"
    assert cleaned.loc[1, "name"] == "Jane Doe"
    assert "Mark123" in cleaned.loc[2, "name"]
    assert metrics["cells_modified"] >= 3


# =============================================================================
# 6. Preview Generation Tests
# =============================================================================

def test_generate_preview():
    df = pd.DataFrame({"x": [1, 2, 2, 3], "y": ["a", "b", "b", "c"]})
    plan = {
        "operation": "remove_duplicates",
        "params": {"subset": None, "keep": "first"},
        "table_name": "test_table"
    }
    preview = DataCleaningEngine.generate_preview(df, plan)
    assert preview["rows_before"] == 4
    assert preview["rows_after"] == 3
    assert preview["rows_affected"] == 1
    assert preview["is_destructive"] is True
    assert len(preview["before_sample"]) == 4
    assert len(preview["after_sample"]) == 3


def test_generate_preview_empty_dataset():
    df = pd.DataFrame(columns=["a", "b"])
    plan = {"operation": "handle_missing", "params": {"strategy": "drop_rows"}}
    preview = DataCleaningEngine.generate_preview(df, plan)
    assert preview["rows_before"] == 0
    assert preview["rows_after"] == 0
    assert preview["rows_affected"] == 0


# =============================================================================
# 7. Conversational Intent Parser Tests
# =============================================================================

def test_parse_cleaning_prompt():
    cols = ["id", "customer_name", "age", "salary"]

    # Missing values
    p1 = DataCleaningEngine.parse_cleaning_prompt("fill missing values in age with median", cols)
    assert p1 is not None
    assert p1["operation"] == "handle_missing"
    assert p1["params"]["strategy"] == "fill_median"
    assert p1["params"]["columns"] == ["age"]

    # Drop missing rows
    p2 = DataCleaningEngine.parse_cleaning_prompt("drop rows with missing values", cols)
    assert p2 is not None
    assert p2["operation"] == "handle_missing"
    assert p2["params"]["strategy"] == "drop_rows"

    # Duplicates
    p3 = DataCleaningEngine.parse_cleaning_prompt("remove all duplicate rows", cols)
    assert p3 is not None
    assert p3["operation"] == "remove_duplicates"

    # Type conversion
    p4 = DataCleaningEngine.parse_cleaning_prompt("convert salary to numeric", cols)
    assert p4 is not None
    assert p4["operation"] == "convert_type"
    assert p4["params"]["column"] == "salary"
    assert p4["params"]["target_type"] == "numeric"

    # Filtering
    p5 = DataCleaningEngine.parse_cleaning_prompt("filter rows where age > 21", cols)
    assert p5 is not None
    assert p5["operation"] == "filter_rows"
    assert p5["params"]["column"] == "age"
    assert p5["params"]["operator"] == ">"
    assert p5["params"]["value"] == 21.0

    # Normalization
    p6 = DataCleaningEngine.parse_cleaning_prompt("strip customer_name and convert to title case", cols)
    assert p6 is not None
    assert p6["operation"] == "normalize_text"
    assert "strip" in p6["params"]["operations"]
    assert "title" in p6["params"]["operations"]

    # Non-cleaning prompt
    p7 = DataCleaningEngine.parse_cleaning_prompt("who are the top 5 customers by salary?", cols)
    assert p7 is None


# =============================================================================
# 8. Reversible Snapshots, Undo & Original Preservation Tests
# =============================================================================

def test_session_snapshot_undo_and_revert(client):
    # Setup session
    res = client.post("/api/v1/auth/session")
    token = res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv_data = b"id,val\n1,100\n2,200\n2,200\n3,300"
    upload_res = client.post(
        "/api/v1/upload",
        headers=headers,
        files={"file": ("raw_data.csv", io.BytesIO(csv_data), "text/csv")}
    )
    assert upload_res.status_code == 200

    # Preview deduplication
    preview_res = client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "remove_duplicates", "params": {"keep": "first"}}
    )
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["rows_before"] == 4
    assert pdata["rows_after"] == 3

    # Apply transformation
    apply_res = client.post("/api/v1/clean/apply", headers=headers)
    assert apply_res.status_code == 200
    assert apply_res.json()["rows_current"] == 3

    # Undo transformation
    undo_res = client.post("/api/v1/clean/undo", headers=headers)
    assert undo_res.status_code == 200
    assert undo_res.json()["rows_restored"] == 4

    # Apply a second transformation (drop rows > 250)
    filter_res = client.post(
        "/api/v1/clean/direct-preview",
        headers=headers,
        json={"operation": "filter_rows", "params": {"column": "val", "operator": "<", "value": 250}}
    )
    assert filter_res.status_code == 200
    client.post("/api/v1/clean/apply", headers=headers)

    # Revert to original
    revert_res = client.post("/api/v1/clean/revert-original", headers=headers)
    assert revert_res.status_code == 200
    assert "restored to original" in revert_res.json()["message"]

    # Verify physical SQL table has 4 rows
    sql_check = client.post("/api/v1/sql/execute", headers=headers, json={"sql": "SELECT count(*) FROM raw_data"}).json()
    assert sql_check["rows"][0][0] == 4


# =============================================================================
# 9. Session Isolation During Data Cleaning
# =============================================================================

def test_session_isolation_cleaning(client):
    # Session A
    res_a = client.post("/api/v1/auth/session")
    token_a = res_a.json()["session_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Session B
    res_b = client.post("/api/v1/auth/session")
    token_b = res_b.json()["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    csv_data = b"id,amount\n1,10\n2,20\n2,20"
    client.post("/api/v1/upload", headers=headers_a, files={"file": ("sales.csv", io.BytesIO(csv_data), "text/csv")})
    client.post("/api/v1/upload", headers=headers_b, files={"file": ("sales.csv", io.BytesIO(csv_data), "text/csv")})

    # Session A cleans data (removes duplicates)
    client.post("/api/v1/clean/direct-preview", headers=headers_a, json={"operation": "remove_duplicates"})
    client.post("/api/v1/clean/apply", headers=headers_a)

    # Session A should have 2 rows
    sql_a = client.post("/api/v1/sql/execute", headers=headers_a, json={"sql": "SELECT count(*) as c FROM sales"}).json()
    assert sql_a["rows"][0][0] == 2

    # Session B MUST still have 3 rows
    sql_b = client.post("/api/v1/sql/execute", headers=headers_b, json={"sql": "SELECT count(*) as c FROM sales"}).json()
    assert sql_b["rows"][0][0] == 3


# =============================================================================
# 10. Conversational Cleaning via /query & /clarify
# =============================================================================

def test_conversational_cleaning_flow(client):
    res = client.post("/api/v1/auth/session")
    token = res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csv = b"item,price\nApple,1.5\nBanana,\nApple,1.5"
    client.post("/api/v1/upload", headers=headers, files={"file": ("groceries.csv", io.BytesIO(csv), "text/csv")})

    # 1. Ask conversational cleaning
    q_res = client.post("/api/v1/query", headers=headers, json={"question": "remove duplicate rows"})
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["status"] == "CLEANING_PREVIEW"
    assert q_data["cleaning_preview"] is not None
    assert q_data["cleaning_preview"]["rows_affected"] == 1

    # 2. Confirm with Clarification "Apply Transformation"
    clarify_res = client.post(
        "/api/v1/clarify",
        headers=headers,
        json={
            "original_question": "remove duplicate rows",
            "clarification_question": q_data["clarification_question"],
            "user_response": "Apply Transformation"
        }
    )
    assert clarify_res.status_code == 200
    c_data = clarify_res.json()
    assert c_data["status"] == "SUCCESS"
    assert "Transformation applied successfully" in c_data["clarification_question"]

    # Verify table now has 2 rows
    sql_res = client.post("/api/v1/sql/execute", headers=headers, json={"sql": "SELECT count(*) FROM groceries"}).json()
    assert sql_res["rows"][0][0] == 2
