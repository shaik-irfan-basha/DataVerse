"""
tests/test_demo_data.py - Automated Unit & Integration Tests for DataVerse Demo Dataset Pack

Verifies:
1. Deterministic generation of all CSV files and SQLite database.
2. Exact row counts and header structures.
3. Relational integrity: primary key uniqueness, foreign key validity, zero orphan orders.
4. Outer join integrity: exactly 11 customers (IDs 90-100) have zero orders.
5. Presence and accuracy of documented intentional data-quality issues (nulls, whitespace, outliers).
6. Execution of canonical example queries against SQLite database.
7. End-to-end compatibility with DataVerse DataConnector and RelationalSchemaEngine.
"""

import os
import csv
import sqlite3
import pytest
import pandas as pd
from pathlib import Path

from sample_data.generate_demo_data import generate_datasets, OUTPUT_DIR
from data_connector import DataConnector
from schema_engine import schema_engine


@pytest.fixture(scope="module")
def demo_data_dir():
    """Ensures demo datasets are generated before running tests."""
    generate_datasets(OUTPUT_DIR)
    return OUTPUT_DIR


def test_demo_files_exist(demo_data_dir):
    """Verifies that all required demo files and documentation exist in sample_data/."""
    expected_files = [
        "customers.csv",
        "orders.csv",
        "products.csv",
        "customers_dirty.csv",
        "retail_demo.sqlite",
        "example_queries.sql",
        "generate_demo_data.py",
        "README.md"
    ]
    for filename in expected_files:
        filepath = demo_data_dir / filename
        assert filepath.exists(), f"Expected demo file missing: {filename}"
        assert filepath.stat().st_size > 0, f"Demo file is empty: {filename}"


def test_csv_row_counts_and_headers(demo_data_dir):
    """Verifies expected row counts and column headers for primary CSV files."""
    # 1. Customers: exactly 100 rows
    df_customers = pd.read_csv(demo_data_dir / "customers.csv", dtype=str)
    assert len(df_customers) == 100
    expected_cust_cols = [
        "customer_id", "first_name", "last_name", "email", "phone",
        "city", "state", "postal_code", "signup_date", "customer_segment"
    ]
    assert list(df_customers.columns) == expected_cust_cols

    # 2. Products: exactly 40 rows
    df_products = pd.read_csv(demo_data_dir / "products.csv", dtype=str)
    assert len(df_products) == 40
    expected_prod_cols = [
        "product_id", "product_name", "category", "price", "cost", "stock_quantity", "status"
    ]
    assert list(df_products.columns) == expected_prod_cols

    # 3. Orders: exactly 250 rows
    df_orders = pd.read_csv(demo_data_dir / "orders.csv", dtype=str)
    assert len(df_orders) == 250
    expected_order_cols = [
        "order_id", "customer_id", "product_id", "order_date", "quantity",
        "unit_price", "total_amount", "status", "payment_method", "shipping_city"
    ]
    assert list(df_orders.columns) == expected_order_cols

    # 4. Dirty Customers: 104 rows (100 + 4 duplicates)
    df_dirty = pd.read_csv(demo_data_dir / "customers_dirty.csv", dtype=str)
    assert len(df_dirty) == 104


def test_relational_integrity_and_foreign_keys(demo_data_dir):
    """Verifies primary key uniqueness, foreign key consistency, and zero orphan records."""
    df_cust = pd.read_csv(demo_data_dir / "customers.csv")
    df_prod = pd.read_csv(demo_data_dir / "products.csv")
    df_orders = pd.read_csv(demo_data_dir / "orders.csv")

    # Primary key uniqueness
    assert df_cust["customer_id"].is_unique
    assert df_prod["product_id"].is_unique
    assert df_orders["order_id"].is_unique

    # No null primary keys
    assert df_cust["customer_id"].notnull().all()
    assert df_prod["product_id"].notnull().all()
    assert df_orders["order_id"].notnull().all()

    # Foreign key validity
    valid_customer_ids = set(df_cust["customer_id"])
    valid_product_ids = set(df_prod["product_id"])

    order_customer_ids = set(df_orders["customer_id"])
    order_product_ids = set(df_orders["product_id"])

    # All order customer_ids must exist in customers
    orphan_customers = order_customer_ids - valid_customer_ids
    assert len(orphan_customers) == 0, f"Found orphan customer_ids in orders: {orphan_customers}"

    # All order product_ids must exist in products
    orphan_products = order_product_ids - valid_product_ids
    assert len(orphan_products) == 0, f"Found orphan product_ids in orders: {orphan_products}"


def test_outer_join_inactive_customers_cohort(demo_data_dir):
    """Verifies that customers 90 through 100 have placed 0 orders (testing outer joins)."""
    df_orders = pd.read_csv(demo_data_dir / "orders.csv")
    active_customers_in_orders = set(df_orders["customer_id"].unique())

    # Customers 90 to 100 must have 0 orders
    for cid in range(90, 101):
        assert cid not in active_customers_in_orders, f"Customer {cid} was expected to have 0 orders"

    # Customers 1 to 89 must all have at least 1 order
    for cid in range(1, 90):
        assert cid in active_customers_in_orders, f"Customer {cid} was expected to have orders"


def test_intentional_data_quality_issues_present(demo_data_dir):
    """Verifies that documented intentional data-quality issues exist as specified."""
    df_cust = pd.read_csv(demo_data_dir / "customers.csv", keep_default_na=False)
    df_prod = pd.read_csv(demo_data_dir / "products.csv", keep_default_na=False)
    df_orders = pd.read_csv(demo_data_dir / "orders.csv", keep_default_na=False)

    # Missing phones in customers: exactly 6
    missing_phones = df_cust[df_cust["phone"] == ""]
    assert len(missing_phones) == 6
    assert set(missing_phones["customer_id"].astype(int)) == {12, 28, 45, 63, 79, 94}

    # Missing postal codes: exactly 4
    missing_zips = df_cust[df_cust["postal_code"] == ""]
    assert len(missing_zips) == 4
    assert set(missing_zips["customer_id"].astype(int)) == {15, 38, 67, 88}

    # Whitespace and casing in city: ID 5 ("  New York"), ID 18 ("seattle")
    cust_5 = df_cust[df_cust["customer_id"] == 5].iloc[0]
    assert cust_5["city"].startswith("  ")
    cust_18 = df_cust[df_cust["customer_id"] == 18].iloc[0]
    assert cust_18["city"] == cust_18["city"].lower()

    # Lowercase states: IDs 8, 24, 49, 82
    for cid in (8, 24, 49, 82):
        row = df_cust[df_cust["customer_id"] == cid].iloc[0]
        assert row["state"] == row["state"].lower()

    # Missing costs in products: IDs 7, 21, 36
    missing_costs = df_prod[df_prod["cost"] == ""]
    assert len(missing_costs) == 3
    assert set(missing_costs["product_id"].astype(int)) == {7, 21, 36}

    # Outliers in orders quantity: exactly 3 bulk orders (25, 30, 40)
    bulk_orders = df_orders[df_orders["quantity"].astype(int) > 20]
    assert len(bulk_orders) == 3
    assert set(bulk_orders["order_id"].astype(int)) == {1042, 1150, 1215}

    # Missing payment methods: IDs 1018, 1077, 1144, 1195, 1238
    missing_pay = df_orders[df_orders["payment_method"] == ""]
    assert len(missing_pay) == 5
    assert set(missing_pay["order_id"].astype(int)) == {1018, 1077, 1144, 1195, 1238}


def test_example_queries_execution(demo_data_dir):
    """Executes the canonical example queries against retail_demo.sqlite and verifies results."""
    db_path = demo_data_dir / "retail_demo.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 1. Customers with their orders
    cur.execute("""
        SELECT COUNT(*)
        FROM customers c
        INNER JOIN orders o ON c.customer_id = o.customer_id
        INNER JOIN products p ON o.product_id = p.product_id;
    """)
    total_joined = cur.fetchone()[0]
    assert total_joined == 250, "All 250 orders should join to customers and products"

    # 2. Inactive customers (no orders)
    cur.execute("""
        SELECT c.customer_id
        FROM customers c
        LEFT JOIN orders o ON c.customer_id = o.customer_id
        WHERE o.order_id IS NULL
        ORDER BY c.customer_id;
    """)
    inactive_cids = [r[0] for r in cur.fetchall()]
    assert inactive_cids == list(range(90, 101)), "Inactive customers must be exactly IDs 90 to 100"

    # 3. Revenue by product
    cur.execute("""
        SELECT p.product_name, SUM(o.total_amount)
        FROM products p
        INNER JOIN orders o ON p.product_id = o.product_id
        GROUP BY p.product_id;
    """)
    prod_revs = cur.fetchall()
    assert len(prod_revs) > 0

    # 4. Outliers query
    cur.execute("""
        SELECT order_id, quantity, total_amount
        FROM orders
        WHERE total_amount >= 1000.00;
    """)
    high_value_orders = cur.fetchall()
    assert len(high_value_orders) >= 3

    conn.close()


def test_dataverse_dataconnector_and_schema_engine_integration(demo_data_dir):
    """Verifies that retail_demo.sqlite and individual CSVs ingest into DataConnector and discover relationships in SchemaEngine."""
    # 1. Test multi-table SQLite ingestion
    connector_sqlite = DataConnector()
    sqlite_path = demo_data_dir / "retail_demo.sqlite"

    tables = connector_sqlite.load_file(str(sqlite_path))
    assert len(tables) == 3
    assert any("customers" in t for t in tables)
    assert any("orders" in t for t in tables)
    assert any("products" in t for t in tables)

    discovered = schema_engine.discover_schema(connector_sqlite)
    rels = schema_engine.infer_relationships(connector_sqlite, discovered)
    assert len(rels) >= 2

    cust_rel = next((r for r in rels if "orders" in r.source_table and "customers" in r.target_table), None)
    assert cust_rel is not None
    assert cust_rel.status in ("confirmed", "inferred")

    prod_rel = next((r for r in rels if "orders" in r.source_table and "products" in r.target_table), None)
    assert prod_rel is not None
    assert prod_rel.status in ("confirmed", "inferred")
    connector_sqlite.connection.close()

    # 2. Test individual CSV ingestion into shared session sandbox
    connector_csv = DataConnector()
    t_cust = connector_csv.load_file(str(demo_data_dir / "customers.csv"))
    t_prod = connector_csv.load_file(str(demo_data_dir / "products.csv"))
    t_ord = connector_csv.load_file(str(demo_data_dir / "orders.csv"))

    assert t_cust == ["customers"]
    assert t_prod == ["products"]
    assert t_ord == ["orders"]

    discovered_csv = schema_engine.discover_schema(connector_csv)
    assert set(discovered_csv.keys()) == {"customers", "products", "orders"}

    rels_csv = schema_engine.infer_relationships(connector_csv, discovered_csv)
    assert len(rels_csv) >= 2
    cust_rel_csv = next((r for r in rels_csv if r.source_table == "orders" and r.target_table == "customers" and r.source_column == "customer_id"), None)
    assert cust_rel_csv is not None
    assert cust_rel_csv.cardinality == "one-to-many"

    connector_csv.connection.close()
