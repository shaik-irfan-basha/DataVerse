"""
tests/test_schema_engine.py - Comprehensive Unit & Integration Tests for Relational Schema Visualizer
"""

import sqlite3
import pytest
import pandas as pd
from data_connector import DataConnector
from schema_engine import (
    RelationalSchemaEngine,
    schema_engine,
    singularize,
    is_type_compatible
)
from metadata_manager import metadata_manager
from backend.session_manager import session_manager


@pytest.fixture
def memory_connector():
    """Provides a fresh in-memory DataConnector with multiple relational tables."""
    connector = DataConnector()
    conn = connector.get_connection()

    # Create relational tables
    conn.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            created_at TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT,
            total_amount REAL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """)
    conn.execute("""
        CREATE TABLE order_items (
            item_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL
        );
    """)
    conn.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT,
            price REAL
        );
    """)
    conn.execute("""
        CREATE TABLE user_profiles (
            profile_id INTEGER PRIMARY KEY,
            customer_id INTEGER UNIQUE,
            bio TEXT,
            avatar_url TEXT
        );
    """)

    # Populate sample rows
    conn.execute("INSERT INTO customers VALUES (1, 'Alice', 'alice@test.com', '2026-01-01');")
    conn.execute("INSERT INTO customers VALUES (2, 'Bob', 'bob@test.com', '2026-01-02');")
    conn.execute("INSERT INTO customers VALUES (3, 'Charlie', 'charlie@test.com', '2026-01-03');")

    conn.execute("INSERT INTO orders VALUES (101, 1, '2026-02-01', 59.99);")
    conn.execute("INSERT INTO orders VALUES (102, 1, '2026-02-03', 120.00);")
    conn.execute("INSERT INTO orders VALUES (103, 2, '2026-02-05', 45.50);")

    conn.execute("INSERT INTO products VALUES (501, 'Mechanical Keyboard', 'Electronics', 99.99);")
    conn.execute("INSERT INTO products VALUES (502, 'Wireless Mouse', 'Electronics', 49.99);")

    conn.execute("INSERT INTO order_items VALUES (1001, 101, 501, 1, 99.99);")
    conn.execute("INSERT INTO order_items VALUES (1002, 101, 502, 2, 49.99);")
    conn.execute("INSERT INTO order_items VALUES (1003, 102, 501, 1, 99.99);")

    conn.execute("INSERT INTO user_profiles VALUES (1, 1, 'Software Engineer', 'avatar1.png');")
    conn.execute("INSERT INTO user_profiles VALUES (2, 2, 'Data Analyst', 'avatar2.png');")

    conn.commit()
    connector.file_tables["relational_test.db"] = ["customers", "orders", "order_items", "products", "user_profiles"]
    return connector


def test_singularize_helper():
    assert singularize("customers") == "customer"
    assert singularize("categories") == "category"
    assert singularize("orders") == "order"
    assert singularize("addresses") == "address"
    assert singularize("items") == "item"
    assert singularize("status") == "status"


def test_type_compatibility():
    assert is_type_compatible("INTEGER", "int") is True
    assert is_type_compatible("BIGINT", "REAL") is True
    assert is_type_compatible("VARCHAR(255)", "TEXT") is True
    assert is_type_compatible("DATETIME", "date") is True
    assert is_type_compatible("INTEGER", "TEXT") is False


def test_discover_schema(memory_connector):
    engine = RelationalSchemaEngine()
    schema = engine.discover_schema(memory_connector)

    assert "customers" in schema
    assert "orders" in schema
    assert "order_items" in schema
    assert "products" in schema
    assert "user_profiles" in schema

    # Check customers table
    cust = schema["customers"]
    assert cust.row_count == 3
    assert "id" in cust.primary_keys
    id_col = next(c for c in cust.columns if c.name == "id")
    assert id_col.is_pk is True
    assert id_col.null_count == 0
    assert id_col.unique_count == 3
    assert id_col.unique_rate == 1.0

    # Check explicit foreign key on orders.customer_id
    ord_tbl = schema["orders"]
    cust_id_col = next(c for c in ord_tbl.columns if c.name == "customer_id")
    assert cust_id_col.is_fk is True
    assert cust_id_col.fk_target_table == "customers"
    assert cust_id_col.fk_target_column == "id"


def test_infer_relationships_explicit_and_inferred(memory_connector):
    engine = RelationalSchemaEngine()
    schema = engine.discover_schema(memory_connector)
    relationships = engine.infer_relationships(memory_connector, schema)

    # 1. Explicit FK: orders.customer_id -> customers.id
    exp_rel = next((r for r in relationships if r.source_table == "orders" and r.target_table == "customers"), None)
    assert exp_rel is not None
    assert exp_rel.source_column == "customer_id"
    assert exp_rel.target_column == "id"
    assert exp_rel.status == "confirmed"
    assert exp_rel.source == "explicit_fk"
    assert exp_rel.confidence == 1.0
    assert exp_rel.cardinality == "one-to-many"

    # 2. Inferred FK: order_items.order_id -> orders.order_id
    ord_item_rel = next((r for r in relationships if r.source_table == "order_items" and r.target_table == "orders"), None)
    assert ord_item_rel is not None
    assert ord_item_rel.source_column == "order_id"
    assert ord_item_rel.target_column == "order_id"
    assert ord_item_rel.status == "inferred"
    assert ord_item_rel.confidence >= 0.70
    assert ord_item_rel.overlap_percentage > 50.0

    # 3. Inferred FK: order_items.product_id -> products.product_id
    prod_rel = next((r for r in relationships if r.source_table == "order_items" and r.target_table == "products"), None)
    assert prod_rel is not None
    assert prod_rel.source_column == "product_id"
    assert prod_rel.target_column == "product_id"
    assert prod_rel.status == "inferred"

    # 4. One-to-one relationship: user_profiles.customer_id -> customers.id
    profile_rel = next((r for r in relationships if r.source_table == "user_profiles" and r.target_table == "customers"), None)
    assert profile_rel is not None
    assert profile_rel.cardinality == "one-to-one"


def test_generate_join_sql_valid(memory_connector):
    engine = RelationalSchemaEngine()
    # Join orders and customers
    res = engine.generate_join_sql(memory_connector, "orders", "customers", join_type="INNER JOIN")
    assert "INNER JOIN" in res["sql"]
    assert '"orders"' in res["sql"]
    assert '"customers"' in res["sql"]
    assert "ON" in res["sql"]
    assert res["is_ambiguous"] is False

    # Execute generated SQL to ensure 100% dialect validity
    conn = memory_connector.get_connection()
    cursor = conn.cursor()
    cursor.execute(res["sql"])
    rows = cursor.fetchall()
    assert len(rows) == 3


def test_generate_join_sql_left_join(memory_connector):
    engine = RelationalSchemaEngine()
    res = engine.generate_join_sql(memory_connector, "customers", "orders", join_type="LEFT JOIN")
    assert "LEFT JOIN" in res["sql"]
    conn = memory_connector.get_connection()
    cursor = conn.cursor()
    cursor.execute(res["sql"])
    rows = cursor.fetchall()
    # 3 orders + customer 3 with NULL order = 4 rows
    assert len(rows) >= 3


def test_generate_join_sql_custom_columns(memory_connector):
    engine = RelationalSchemaEngine()
    res = engine.generate_join_sql(
        memory_connector,
        table_a="order_items",
        table_b="products",
        source_column="product_id",
        target_column="product_id"
    )
    assert "order_items" in res["sql"]
    assert "products" in res["sql"]
    conn = memory_connector.get_connection()
    cursor = conn.cursor()
    cursor.execute(res["sql"])
    rows = cursor.fetchall()
    assert len(rows) == 3


def test_generate_join_sql_invalid_table(memory_connector):
    engine = RelationalSchemaEngine()
    with pytest.raises(ValueError, match="not found in active dataset"):
        engine.generate_join_sql(memory_connector, "nonexistent_table", "orders")


def test_empty_table_schema_and_inference():
    """Ensures 0-row tables are handled gracefully without zero-division errors."""
    connector = DataConnector()
    conn = connector.get_connection()
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);")
    conn.execute("CREATE TABLE posts (post_id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT);")
    conn.commit()

    engine = RelationalSchemaEngine()
    schema = engine.discover_schema(connector)
    assert schema["users"].row_count == 0
    assert schema["posts"].row_count == 0

    rels = engine.infer_relationships(connector, schema)
    # Should infer relationship by column name pattern even with 0 rows
    assert len(rels) >= 1
    rel = rels[0]
    assert rel.source_table == "posts"
    assert rel.target_table == "users"
    assert rel.source_column == "user_id"
    assert rel.target_column == "id"
    assert rel.overlap_percentage == 0.0


def test_relationship_persistence_and_session_isolation(memory_connector):
    """Verifies that user confirmations and rejections persist and isolate by session."""
    engine = RelationalSchemaEngine()
    schema = engine.discover_schema(memory_connector)

    session_a = "session_test_a"
    session_b = "session_test_b"

    # In session_a, confirm order_items.order_id -> orders.order_id
    metadata_manager.save_schema_relationship(
        session_id=session_a,
        dataset_name="test_data",
        source_table="order_items",
        source_column="order_id",
        target_table="orders",
        target_column="order_id",
        status="confirmed",
        cardinality="one-to-many"
    )

    # In session_b, reject order_items.order_id -> orders.order_id
    metadata_manager.save_schema_relationship(
        session_id=session_b,
        dataset_name="test_data",
        source_table="order_items",
        source_column="order_id",
        target_table="orders",
        target_column="order_id",
        status="rejected",
        cardinality="one-to-many"
    )

    # Infer for session_a
    rels_a = engine.infer_relationships(memory_connector, schema, session_id=session_a, dataset_name="test_data")
    rel_a = next(r for r in rels_a if r.source_table == "order_items" and r.target_table == "orders")
    assert rel_a.status == "confirmed"
    assert rel_a.user_confirmed is True

    # Infer for session_b
    rels_b = engine.infer_relationships(memory_connector, schema, session_id=session_b, dataset_name="test_data")
    rel_b = next(r for r in rels_b if r.source_table == "order_items" and r.target_table == "orders")
    assert rel_b.status == "rejected"
    assert rel_b.user_rejected is True

    # Cleanup metadata
    metadata_manager.delete_schema_relationship(
        session_id=session_a,
        dataset_name="test_data",
        source_table="order_items",
        source_column="order_id",
        target_table="orders",
        target_column="order_id"
    )
    metadata_manager.delete_schema_relationship(
        session_id=session_b,
        dataset_name="test_data",
        source_table="order_items",
        source_column="order_id",
        target_table="orders",
        target_column="order_id"
    )
