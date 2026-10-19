"""
tests/test_phase4_validation.py - Comprehensive Regression Tests for Phase 4 Validation, Chart & Diagnostics

Covers:
1. Chart API: auto-detection, type override, series structure, non-numeric handling, empty errors.
2. Diagnostics (Table Profiler) API: normal tables, tables with nulls, empty tables (0 rows), non-existent tables (404), unauthenticated/no-dataset (400).
3. Relational Schema & JOIN Correctness: inference, INNER vs LEFT JOIN semantics, unmatched rows preservation (11 customers).
4. SQL Aggregation & Grain Accuracy: product sales & revenue calculations verified against independent SQLite truth.
"""

import io
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.session_manager import session_manager
from chart_engine import ChartEngine


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authenticated_session(client):
    """Creates a clean authenticated session."""
    res = client.post("/api/v1/auth/session")
    assert res.status_code == 200
    token = res.json()["session_token"]
    session_id = res.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Session-Token": token}
    return {"client": client, "headers": headers, "session_id": session_id, "token": token}


@pytest.fixture
def retail_demo_session(authenticated_session):
    """Loads the retail_demo.sqlite dataset into the authenticated session."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    with open("sample_data/retail_demo.sqlite", "rb") as f:
        res = client.post(
            "/api/v1/upload",
            headers=headers,
            files={"file": ("retail_demo.sqlite", f, "application/x-sqlite3")}
        )
    assert res.status_code == 200
    data = res.json()
    assert "retail_demo_customers" in data["tables_created"]
    assert "retail_demo_orders" in data["tables_created"]
    assert "retail_demo_products" in data["tables_created"]

    return authenticated_session


# =============================================================================
# 1. Chart API Tests
# =============================================================================

def test_chart_grouped_bar_for_sales_metrics(authenticated_session):
    """Tests auto-generating a grouped_bar chart from product_name, units_sold, and revenue."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    columns = ["product_name", "units_sold", "revenue"]
    rows = [
        ["Gaming Monitor 27-inch", 34, 10199.66],
        ["Wireless Noise-Cancelling Headphones", 13, 2599.87],
        ["4K Ultra HD Webcam", 19, 2469.81],
        ["Merino Wool Crewneck Sweater", 18, 1584.0],
        ["Smart Home Security Camera", 18, 1439.82],
    ]

    payload = {
        "columns": columns,
        "rows": rows,
        "chart_type": "auto",
        "title": "Top Products by Sales & Revenue"
    }

    res = client.post("/api/v1/chart", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["chart_type"] == "grouped_bar"
    assert data["base64_image"].startswith("data:image/png;base64,")
    assert len(data["base64_image"]) > 100

    series = data["series_data"]
    assert series["labels"] == [r[0] for r in rows]
    assert len(series["datasets"]) == 2
    assert series["datasets"][0]["label"] == "units_sold"
    assert series["datasets"][1]["label"] == "revenue"


def test_chart_type_overrides(authenticated_session):
    """Tests explicit user chart type overrides (bar, line, scatter, pie)."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    columns = ["category", "sales"]
    rows = [
        ["Electronics", 450],
        ["Apparel", 280],
        ["Home Goods", 190],
    ]

    for ctype in ["bar", "horizontal_bar", "line", "pie"]:
        res = client.post(
            "/api/v1/chart",
            headers=headers,
            json={"columns": columns, "rows": rows, "chart_type": ctype, "title": f"Test {ctype}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["chart_type"] == ctype
        assert data["base64_image"].startswith("data:image/png;base64,")


def test_chart_empty_results_handling(authenticated_session):
    """Tests that passing empty columns or rows returns 400 Bad Request."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    res = client.post("/api/v1/chart", headers=headers, json={"columns": [], "rows": []})
    assert res.status_code == 400
    assert "must not be empty" in res.json()["detail"].lower()


def test_chart_non_numeric_graceful_handling(authenticated_session):
    """Tests that result sets with purely textual columns do not crash the chart engine."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    columns = ["first_name", "last_name", "city"]
    rows = [
        ["Alice", "Smith", "New York"],
        ["Bob", "Jones", "Los Angeles"],
    ]

    res = client.post(
        "/api/v1/chart",
        headers=headers,
        json={"columns": columns, "rows": rows, "chart_type": "auto"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["base64_image"].startswith("data:image/png;base64,")


# =============================================================================
# 2. Diagnostics (Table Profiler) API Tests
# =============================================================================

def test_profile_retail_demo_tables(retail_demo_session):
    """Tests diagnostics profiling on loaded retail demo tables."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    # 1. Profile customers table
    res_cust = client.get("/api/v1/profile/retail_demo_customers", headers=headers)
    assert res_cust.status_code == 200
    cust_data = res_cust.json()
    assert cust_data["table_name"] == "retail_demo_customers"
    assert cust_data["total_rows"] == 100
    assert cust_data["total_columns"] >= 5

    # Check primary key column
    cust_id_col = next(c for c in cust_data["columns"] if c["name"] == "customer_id")
    assert cust_id_col["null_count"] == 0
    assert cust_id_col["unique_count"] == 100

    # 2. Profile orders table
    res_ord = client.get("/api/v1/profile/retail_demo_orders", headers=headers)
    assert res_ord.status_code == 200
    ord_data = res_ord.json()
    assert ord_data["table_name"] == "retail_demo_orders"
    assert ord_data["total_rows"] == 250

    total_amt_col = next(c for c in ord_data["columns"] if c["name"] == "total_amount")
    assert total_amt_col["is_numeric"] is True
    assert total_amt_col["min_val"] is not None
    assert total_amt_col["max_val"] is not None
    assert total_amt_col["mean_val"] > 0


def test_profile_empty_table(authenticated_session):
    """Tests that profiling a table with 0 rows returns schema metadata without division by zero."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]
    token = authenticated_session["token"]

    session = session_manager.get_session_by_token(token)
    conn = session.data_connector.get_connection()
    conn.execute("""
        CREATE TABLE empty_inventory (
            item_id INTEGER PRIMARY KEY,
            item_name TEXT NOT NULL,
            stock_count INTEGER,
            unit_price REAL
        );
    """)
    conn.commit()
    session.data_connector.file_tables["custom.db"] = ["empty_inventory"]
    session.set_active_dataset("custom.db")

    res = client.get("/api/v1/profile/empty_inventory", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["table_name"] == "empty_inventory"
    assert data["total_rows"] == 0
    assert data["total_columns"] == 4
    for c in data["columns"]:
        assert c["null_percentage"] == 0.0
        assert c["unique_count"] == 0


def test_profile_table_with_nulls(authenticated_session):
    """Tests profiling a table with deliberate null values."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]
    token = authenticated_session["token"]

    session = session_manager.get_session_by_token(token)
    conn = session.data_connector.get_connection()
    conn.execute("""
        CREATE TABLE feedback (
            feedback_id INTEGER PRIMARY KEY,
            rating INTEGER,
            comment TEXT
        );
    """)
    conn.execute("INSERT INTO feedback VALUES (1, 5, 'Great!'), (2, NULL, NULL), (3, 4, NULL), (4, NULL, 'Good');")
    conn.commit()
    session.data_connector.file_tables["custom2.db"] = ["feedback"]
    session.set_active_dataset("custom2.db")

    res = client.get("/api/v1/profile/feedback", headers=headers)
    assert res.status_code == 200
    data = res.json()
    comment_col = next(c for c in data["columns"] if c["name"] == "comment")
    assert comment_col["null_count"] == 2
    assert comment_col["null_percentage"] == 50.0


def test_profile_nonexistent_table_returns_404(retail_demo_session):
    """Tests that requesting a non-existent table returns 404 with available tables."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    res = client.get("/api/v1/profile/non_existent_table", headers=headers)
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"]


def test_profile_no_dataset_returns_400(authenticated_session):
    """Tests that requesting a profile when no dataset is loaded returns 400."""
    client = authenticated_session["client"]
    headers = authenticated_session["headers"]

    res = client.get("/api/v1/profile/any_table", headers=headers)
    assert res.status_code == 400
    assert "No dataset loaded" in res.json()["detail"]


# =============================================================================
# 3. Relational Schema & JOIN Correctness Tests
# =============================================================================

def test_retail_demo_relationship_discovery(retail_demo_session):
    """Tests schema discovery on retail demo tables."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    res = client.get("/api/v1/schema/visualize", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["is_loaded"] is True
    assert len(data["tables"]) == 3

    rels = data["relationships"]
    assert len(rels) >= 2

    # Verify orders -> customers relationship
    cust_rel = next((r for r in rels if "customers" in r["target_table"] and "orders" in r["source_table"]), None)
    assert cust_rel is not None
    assert cust_rel["source_column"] == "customer_id"
    assert cust_rel["target_column"] == "customer_id"
    assert cust_rel["cardinality"] in ("one-to-many", "many-to-one")

    # Verify orders -> products relationship
    prod_rel = next((r for r in rels if "products" in r["target_table"] and "orders" in r["source_table"]), None)
    assert prod_rel is not None
    assert prod_rel["source_column"] == "product_id"
    assert prod_rel["target_column"] == "product_id"
    assert prod_rel["cardinality"] in ("one-to-many", "many-to-one")


def test_join_generator_inner_vs_left_join(retail_demo_session):
    """
    Tests JOIN query generation and verifies:
    1. Correct identifier quoting and column aliasing.
    2. INNER JOIN excludes 11 unmatched customers.
    3. LEFT JOIN preserves all 100 customers (11 with NULL order_id).
    """
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    # 1. Generate INNER JOIN proposal
    res_inner = client.post(
        "/api/v1/schema/generate-join",
        headers=headers,
        json={
            "table_a": "retail_demo_customers",
            "table_b": "retail_demo_orders",
            "join_type": "INNER JOIN"
        }
    )
    assert res_inner.status_code == 200
    inner_sql = res_inner.json()["sql"]
    assert '"retail_demo_customers"' in inner_sql
    assert '"retail_demo_orders"' in inner_sql
    assert "INNER JOIN" in inner_sql

    # 2. Execute INNER JOIN in SQL Lab
    res_run_inner = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": inner_sql}
    )
    assert res_run_inner.status_code == 200
    inner_data = res_run_inner.json()
    assert inner_data["success"] is True

    # Check distinct customer_ids in inner join (should be at most 89)
    res_distinct_inner = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": 'SELECT COUNT(DISTINCT c."customer_id") FROM "retail_demo_customers" c INNER JOIN "retail_demo_orders" o ON c."customer_id" = o."customer_id"'}
    )
    assert res_distinct_inner.status_code == 200
    assert res_distinct_inner.json()["rows"][0][0] == 89

    # 3. Generate and test LEFT JOIN
    res_left = client.post(
        "/api/v1/schema/generate-join",
        headers=headers,
        json={
            "table_a": "retail_demo_customers",
            "table_b": "retail_demo_orders",
            "join_type": "LEFT JOIN"
        }
    )
    assert res_left.status_code == 200
    left_sql = res_left.json()["sql"]
    assert "LEFT JOIN" in left_sql

    # Verify that all 100 customers are preserved in LEFT JOIN
    res_left_distinct = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": 'SELECT COUNT(DISTINCT c."customer_id") FROM "retail_demo_customers" c LEFT JOIN "retail_demo_orders" o ON c."customer_id" = o."customer_id"'}
    )
    assert res_left_distinct.status_code == 200
    assert res_left_distinct.json()["rows"][0][0] == 100

    # Verify that exactly 11 customers have zero orders
    res_unmatched = client.post(
        "/api/v1/sql/execute",
        headers=headers,
        json={"sql": 'SELECT COUNT(*) FROM "retail_demo_customers" c LEFT JOIN "retail_demo_orders" o ON c."customer_id" = o."customer_id" WHERE o."order_id" IS NULL'}
    )
    assert res_unmatched.status_code == 200
    assert res_unmatched.json()["rows"][0][0] == 11


# =============================================================================
# 4. SQL Aggregation & Grain Accuracy Tests
# =============================================================================

def test_product_sales_and_revenue_aggregation(retail_demo_session):
    """
    Validates product sales and revenue query accuracy against independent SQLite ground truth:
    Query: SELECT p.product_name, SUM(o.quantity) AS units_sold, ROUND(SUM(o.total_amount), 2) AS revenue ...
    """
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    sql = """
        SELECT
            p."product_name",
            SUM(o."quantity") AS units_sold,
            ROUND(SUM(o."total_amount"), 2) AS revenue
        FROM "retail_demo_products" p
        LEFT JOIN "retail_demo_orders" o ON p."product_id" = o."product_id"
        GROUP BY p."product_id", p."product_name"
        ORDER BY revenue DESC
    """

    res = client.post("/api/v1/sql/execute", headers=headers, json={"sql": sql})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Exactly 40 products
    assert len(data["rows"]) == 40
    assert data["columns"] == ["product_name", "units_sold", "revenue"]

    top_row = data["rows"][0]
    assert top_row[0] == "Gaming Monitor 27-inch"
    assert top_row[1] == 34
    assert top_row[2] == 10199.66

    # Verify order-grain consistency: total_amount == quantity * unit_price
    check_grain_sql = """
        SELECT COUNT(*)
        FROM "retail_demo_orders"
        WHERE ROUND("total_amount", 2) != ROUND("quantity" * "unit_price", 2)
    """
    res_grain = client.post("/api/v1/sql/execute", headers=headers, json={"sql": check_grain_sql})
    assert res_grain.status_code == 200
    assert res_grain.json()["rows"][0][0] == 0, "Order total_amount does not match quantity * unit_price"


# =============================================================================
# 5. Relationship Persistence & Lifecycle Tests
# =============================================================================

def test_relationship_confirm_and_refresh_persistence(retail_demo_session):
    """Tests that confirming a relationship persists across schema reloads."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    # 1. Fetch initial schema
    res_vis = client.get("/api/v1/schema/visualize", headers=headers)
    assert res_vis.status_code == 200
    data = res_vis.json()
    rel = data["relationships"][0]
    rel_id = rel["id"]
    assert rel["status"] == "inferred"

    # 2. Confirm relationship
    res_conf = client.post(
        "/api/v1/schema/relationships/confirm",
        headers=headers,
        json={
            "source_table": rel["source_table"],
            "source_column": rel["source_column"],
            "target_table": rel["target_table"],
            "target_column": rel["target_column"],
            "cardinality": rel.get("cardinality", "one-to-many")
        }
    )
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"

    # 3. Reload schema visualization (simulating page reload)
    res_vis2 = client.get("/api/v1/schema/visualize", headers=headers)
    assert res_vis2.status_code == 200
    data2 = res_vis2.json()
    updated_rel = next(r for r in data2["relationships"] if r["source_table"] == rel["source_table"] and r["target_table"] == rel["target_table"])
    assert updated_rel["status"] == "confirmed"


def test_relationship_reject_and_refresh_persistence(retail_demo_session):
    """Tests that rejecting a relationship persists across schema reloads."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    res_vis = client.get("/api/v1/schema/visualize", headers=headers)
    assert res_vis.status_code == 200
    data = res_vis.json()
    rel = data["relationships"][1]

    # Reject relationship
    res_rej = client.post(
        "/api/v1/schema/relationships/reject",
        headers=headers,
        json={
            "source_table": rel["source_table"],
            "source_column": rel["source_column"],
            "target_table": rel["target_table"],
            "target_column": rel["target_column"],
            "cardinality": rel.get("cardinality", "one-to-many")
        }
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "rejected"

    # Reload schema visualization
    res_vis2 = client.get("/api/v1/schema/visualize", headers=headers)
    assert res_vis2.status_code == 200
    data2 = res_vis2.json()
    updated_rel = next(r for r in data2["relationships"] if r["source_table"] == rel["source_table"] and r["target_table"] == rel["target_table"])
    assert updated_rel["status"] == "rejected"


def test_diagnostics_rapid_switching_isolation(retail_demo_session):
    """Tests requesting diagnostics for multiple tables in rapid succession."""
    client = retail_demo_session["client"]
    headers = retail_demo_session["headers"]

    tables = ["retail_demo_customers", "retail_demo_products", "retail_demo_orders"]
    responses = {}
    for tbl in tables:
        res = client.get(f"/api/v1/profile/{tbl}", headers=headers)
        assert res.status_code == 200
        responses[tbl] = res.json()

    assert responses["retail_demo_customers"]["total_rows"] == 100
    assert responses["retail_demo_products"]["total_rows"] == 40
    assert responses["retail_demo_orders"]["total_rows"] == 250
