"""
tests/test_schema_endpoints.py - Integration Tests for Schema Visualizer API Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.session_manager import session_manager


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_with_data(client):
    """Initializes an authenticated session with a multi-table relational dataset."""
    res = client.post("/api/v1/auth/session")
    assert res.status_code == 200
    token = res.json()["session_token"]
    session_id = res.json()["session_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Session-Token": token}

    # Populate session's in-memory SQLite database
    session = session_manager.get_session_by_token(token)
    conn = session.data_connector.get_connection()
    conn.execute("""
        CREATE TABLE departments (
            dept_id INTEGER PRIMARY KEY,
            dept_name TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE employees (
            emp_id INTEGER PRIMARY KEY,
            emp_name TEXT NOT NULL,
            dept_id INTEGER,
            salary REAL
        );
    """)
    conn.execute("INSERT INTO departments VALUES (10, 'Engineering'), (20, 'Product'), (30, 'Design');")
    conn.execute("INSERT INTO employees VALUES (1, 'Eve', 10, 110000), (2, 'Dan', 10, 95000), (3, 'Mallory', 20, 105000);")
    conn.commit()

    session.data_connector.file_tables["company.db"] = ["departments", "employees"]
    session.set_active_dataset("company.db")

    return {"client": client, "headers": headers, "session_id": session_id, "token": token}


def test_schema_visualize_empty_session(client):
    res = client.post("/api/v1/auth/session")
    token = res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/schema/visualize", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_loaded"] is False
    assert data["table_count"] == 0
    assert data["relationships"] == []


def test_schema_visualize_with_tables(session_with_data):
    client = session_with_data["client"]
    headers = session_with_data["headers"]

    res = client.get("/api/v1/schema/visualize", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_loaded"] is True
    assert data["table_count"] == 2
    assert len(data["tables"]) == 2

    # Check inferred relationship: employees.dept_id -> departments.dept_id
    rels = data["relationships"]
    assert len(rels) >= 1
    dept_rel = next((r for r in rels if r["source_table"] == "employees" and r["target_table"] == "departments"), None)
    assert dept_rel is not None
    assert dept_rel["source_column"] == "dept_id"
    assert dept_rel["target_column"] == "dept_id"
    assert dept_rel["status"] == "inferred"
    assert dept_rel["cardinality"] == "one-to-many"
    assert dept_rel["overlap_percentage"] > 50.0


def test_confirm_and_reject_relationship_endpoints(session_with_data):
    client = session_with_data["client"]
    headers = session_with_data["headers"]

    # 1. Confirm relationship
    confirm_res = client.post("/api/v1/schema/relationships/confirm", json={
        "source_table": "employees",
        "source_column": "dept_id",
        "target_table": "departments",
        "target_column": "dept_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["success"] is True
    assert confirm_data["status"] == "confirmed"

    # Verify visualizer now reports confirmed
    vis_res = client.get("/api/v1/schema/visualize", headers=headers)
    vis_data = vis_res.json()
    dept_rel = next(r for r in vis_data["relationships"] if r["source_table"] == "employees" and r["target_table"] == "departments")
    assert dept_rel["status"] == "confirmed"
    assert dept_rel["user_confirmed"] is True

    # 2. Reject relationship
    reject_res = client.post("/api/v1/schema/relationships/reject", json={
        "source_table": "employees",
        "source_column": "dept_id",
        "target_table": "departments",
        "target_column": "dept_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert reject_res.status_code == 200
    reject_data = reject_res.json()
    assert reject_data["success"] is True
    assert reject_data["status"] == "rejected"

    # Verify visualizer now reports rejected
    vis_res2 = client.get("/api/v1/schema/visualize", headers=headers)
    vis_data2 = vis_res2.json()
    dept_rel2 = next(r for r in vis_data2["relationships"] if r["source_table"] == "employees" and r["target_table"] == "departments")
    assert dept_rel2["status"] == "rejected"
    assert dept_rel2["user_rejected"] is True


def test_create_and_delete_custom_relationship(session_with_data):
    client = session_with_data["client"]
    headers = session_with_data["headers"]

    # Create custom relationship
    res = client.post("/api/v1/schema/relationships/custom", json={
        "source_table": "employees",
        "source_column": "emp_name",
        "target_table": "departments",
        "target_column": "dept_name",
        "cardinality": "one-to-one"
    }, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Delete custom relationship
    del_res = client.delete(
        "/api/v1/schema/relationships?source_table=employees&source_column=emp_name&target_table=departments&target_column=dept_name",
        headers=headers
    )
    assert del_res.status_code == 200
    assert "removed" in del_res.json()["message"]


def test_generate_join_endpoint(session_with_data):
    client = session_with_data["client"]
    headers = session_with_data["headers"]

    res = client.post("/api/v1/schema/generate-join", json={
        "table_a": "employees",
        "table_b": "departments",
        "join_type": "INNER JOIN"
    }, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "SELECT" in data["sql"]
    assert "INNER JOIN" in data["sql"]
    assert "departments" in data["sql"]
    assert "employees" in data["sql"]
    assert data["is_ambiguous"] is False


def test_session_isolation_in_visualizer(session_with_data, client):
    """Ensures Session B cannot see or manipulate Session A's schema relationships."""
    headers_a = session_with_data["headers"]

    # Create fresh second session
    res_b = client.post("/api/v1/auth/session")
    token_b = res_b.json()["session_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Session A confirms a relationship
    client.post("/api/v1/schema/relationships/confirm", json={
        "source_table": "employees",
        "source_column": "dept_id",
        "target_table": "departments",
        "target_column": "dept_id"
    }, headers=headers_a)

    # Session B queries visualizer - has 0 tables and 0 relationships
    vis_b = client.get("/api/v1/schema/visualize", headers=headers_b)
    assert vis_b.status_code == 200
    data_b = vis_b.json()
    assert data_b["table_count"] == 0
    assert len(data_b["relationships"]) == 0


def test_relationship_counters_lifecycle(client):
    """
    Regression test verifying Schema Studio relationship counters across their full lifecycle:
    1. Empty relationship list (0 Confirmed, 0 Inferred, 0 Rejected)
    2. Inferred relationships detected from schema
    3. Multiple confirmed relationships (2 Confirmed)
    4. Rejected relationships (1 Confirmed, 1 Rejected)
    5. Immediate persistence and reload of persisted counts
    """
    # 1. Empty session
    res_empty = client.post("/api/v1/auth/session")
    token_empty = res_empty.json()["session_token"]
    headers_empty = {"Authorization": f"Bearer {token_empty}"}

    vis_empty = client.get("/api/v1/schema/visualize", headers=headers_empty)
    assert vis_empty.status_code == 200
    d_empty = vis_empty.json()
    assert d_empty["confirmed_count"] == 0
    assert d_empty["inferred_count"] == 0
    assert d_empty["rejected_count"] == 0
    assert len(d_empty["relationships"]) == 0

    # 2. Multi-table session with 2 relationships (customers, orders, products)
    res = client.post("/api/v1/auth/session")
    token = res.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    session = session_manager.get_session_by_token(token)

    conn = session.data_connector.get_connection()
    conn.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id INTEGER
        );
    """)
    conn.execute("INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob');")
    conn.execute("INSERT INTO products VALUES (101, 'Widget'), (102, 'Gizmo');")
    conn.execute("INSERT INTO orders VALUES (1001, 1, 101), (1002, 2, 102);")
    conn.commit()

    session.data_connector.file_tables["retail.db"] = ["customers", "products", "orders"]
    session.set_active_dataset("retail.db")

    # Fetch initial schema visualizer data
    vis_init = client.get("/api/v1/schema/visualize", headers=headers)
    assert vis_init.status_code == 200
    d_init = vis_init.json()
    assert d_init["table_count"] == 3
    assert len(d_init["relationships"]) == 2
    assert d_init["confirmed_count"] == 0
    assert d_init["inferred_count"] == 2
    assert d_init["rejected_count"] == 0

    # 3. Confirm first relationship: orders.customer_id -> customers.customer_id
    conf1 = client.post("/api/v1/schema/relationships/confirm", json={
        "source_table": "orders",
        "source_column": "customer_id",
        "target_table": "customers",
        "target_column": "customer_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert conf1.status_code == 200

    vis_1conf = client.get("/api/v1/schema/visualize", headers=headers)
    d_1conf = vis_1conf.json()
    assert d_1conf["confirmed_count"] == 1
    assert d_1conf["inferred_count"] == 1
    assert d_1conf["rejected_count"] == 0

    # Confirm second relationship: orders.product_id -> products.product_id
    conf2 = client.post("/api/v1/schema/relationships/confirm", json={
        "source_table": "orders",
        "source_column": "product_id",
        "target_table": "products",
        "target_column": "product_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert conf2.status_code == 200

    # Now TWO confirmed relationships
    vis_2conf = client.get("/api/v1/schema/visualize", headers=headers)
    d_2conf = vis_2conf.json()
    assert d_2conf["confirmed_count"] == 2
    assert d_2conf["inferred_count"] == 0
    assert d_2conf["rejected_count"] == 0
    confirmed_rels = [r for r in d_2conf["relationships"] if r["status"] == "confirmed"]
    assert len(confirmed_rels) == 2

    # 4. Reject one relationship: orders.product_id -> products.product_id
    rej1 = client.post("/api/v1/schema/relationships/reject", json={
        "source_table": "orders",
        "source_column": "product_id",
        "target_table": "products",
        "target_column": "product_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert rej1.status_code == 200

    vis_rej = client.get("/api/v1/schema/visualize", headers=headers)
    d_rej = vis_rej.json()
    assert d_rej["confirmed_count"] == 1
    assert d_rej["inferred_count"] == 0
    assert d_rej["rejected_count"] == 1

    # Reject the other relationship: orders.customer_id -> customers.customer_id
    rej2 = client.post("/api/v1/schema/relationships/reject", json={
        "source_table": "orders",
        "source_column": "customer_id",
        "target_table": "customers",
        "target_column": "customer_id",
        "cardinality": "one-to-many"
    }, headers=headers)
    assert rej2.status_code == 200

    vis_2rej = client.get("/api/v1/schema/visualize", headers=headers)
    d_2rej = vis_2rej.json()
    assert d_2rej["confirmed_count"] == 0
    assert d_2rej["inferred_count"] == 0
    assert d_2rej["rejected_count"] == 2

    # 5. Reload persisted metadata (new request simulates refreshing Schema Studio)
    vis_reload = client.get("/api/v1/schema/visualize", headers=headers)
    assert vis_reload.status_code == 200
    d_reload = vis_reload.json()
    assert d_reload["confirmed_count"] == 0
    assert d_reload["inferred_count"] == 0
    assert d_reload["rejected_count"] == 2


def test_frontend_state_and_ui_counter_integration():
    """
    Verifies frontend state counting and badge string formatting contracts using Node.js.
    Tests:
    - Empty relationship list -> '0 Confirmed • 0 Inferred'
    - Inferred relationships -> '0 Confirmed • 2 Inferred'
    - Two confirmed relationships -> '2 Confirmed • 0 Inferred'
    - Rejected relationships -> '1 Confirmed • 0 Inferred • 1 Rejected'
    - camelCase and snake_case parity in AppState
    """
    import subprocess
    node_script = """
    import { AppState } from './frontend/js/state.js';
    import { UIController } from './frontend/js/ui.js';
    import assert from 'node:assert';

    const ui = new UIController();
    const appState = new AppState();

    // 1. Empty relationship list
    appState.setSchemaVisualizerData({ is_loaded: false, tables: [], relationships: [] });
    assert.strictEqual(appState.schemaVisualizer.confirmedCount, 0);
    assert.strictEqual(appState.schemaVisualizer.confirmed_count, 0);
    assert.strictEqual(appState.schemaVisualizer.inferredCount, 0);
    assert.strictEqual(appState.schemaVisualizer.inferred_count, 0);
    assert.strictEqual(appState.schemaVisualizer.rejectedCount, 0);
    assert.strictEqual(appState.schemaVisualizer.rejected_count, 0);
    assert.strictEqual(
      ui.formatRelationshipCount(appState.schemaVisualizer.confirmedCount, appState.schemaVisualizer.inferredCount, appState.schemaVisualizer.rejectedCount),
      '0 Confirmed • 0 Inferred'
    );

    // 2. Inferred relationships
    appState.setSchemaVisualizerData({
      is_loaded: true,
      tables: [{ table_name: 'orders' }, { table_name: 'customers' }],
      relationships: [
        { id: 'orders.customer_id->customers.id', status: 'inferred' },
        { id: 'orders.product_id->products.id', status: 'inferred' }
      ]
    });
    assert.strictEqual(appState.schemaVisualizer.confirmedCount, 0);
    assert.strictEqual(appState.schemaVisualizer.confirmed_count, 0);
    assert.strictEqual(appState.schemaVisualizer.inferredCount, 2);
    assert.strictEqual(appState.schemaVisualizer.inferred_count, 2);
    assert.strictEqual(
      ui.formatRelationshipCount(appState.schemaVisualizer.confirmedCount, appState.schemaVisualizer.inferredCount, appState.schemaVisualizer.rejectedCount),
      '0 Confirmed • 2 Inferred'
    );

    // 3. Two confirmed relationships
    appState.updateRelationshipStatus('orders.customer_id->customers.id', 'confirmed');
    appState.updateRelationshipStatus('orders.product_id->products.id', 'confirmed');
    assert.strictEqual(appState.schemaVisualizer.confirmedCount, 2);
    assert.strictEqual(appState.schemaVisualizer.confirmed_count, 2);
    assert.strictEqual(appState.schemaVisualizer.inferredCount, 0);
    assert.strictEqual(appState.schemaVisualizer.inferred_count, 0);
    assert.strictEqual(
      ui.formatRelationshipCount(appState.schemaVisualizer.confirmedCount, appState.schemaVisualizer.inferredCount, appState.schemaVisualizer.rejectedCount),
      '2 Confirmed • 0 Inferred'
    );

    // 4. One confirmed, one rejected
    appState.updateRelationshipStatus('orders.product_id->products.id', 'rejected');
    assert.strictEqual(appState.schemaVisualizer.confirmedCount, 1);
    assert.strictEqual(appState.schemaVisualizer.confirmed_count, 1);
    assert.strictEqual(appState.schemaVisualizer.rejectedCount, 1);
    assert.strictEqual(appState.schemaVisualizer.rejected_count, 1);
    assert.strictEqual(
      ui.formatRelationshipCount(appState.schemaVisualizer.confirmedCount, appState.schemaVisualizer.inferredCount, appState.schemaVisualizer.rejectedCount),
      '1 Confirmed • 0 Inferred • 1 Rejected'
    );

    // 5. Reloading persisted metadata
    appState.setSchemaVisualizerData({
      is_loaded: true,
      confirmed_count: 2,
      inferred_count: 0,
      rejected_count: 0,
      relationships: [
        { id: 'orders.customer_id->customers.id', status: 'confirmed' },
        { id: 'orders.product_id->products.id', status: 'confirmed' }
      ]
    });
    assert.strictEqual(appState.schemaVisualizer.confirmedCount, 2);
    assert.strictEqual(appState.schemaVisualizer.confirmed_count, 2);
    assert.strictEqual(appState.schemaVisualizer.inferredCount, 0);
    assert.strictEqual(appState.schemaVisualizer.inferred_count, 0);
    assert.strictEqual(
      ui.formatRelationshipCount(appState.schemaVisualizer.confirmedCount, appState.schemaVisualizer.inferredCount, appState.schemaVisualizer.rejectedCount),
      '2 Confirmed • 0 Inferred'
    );
    """
    proc = subprocess.run(["node", "--input-type=module", "-e", node_script], capture_output=True, text=True)
    assert proc.returncode == 0, f"Node test failed with error: {proc.stderr}"
