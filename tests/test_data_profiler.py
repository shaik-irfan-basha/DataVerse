import pytest
from data_connector import DataConnector
from data_profiler import DataProfiler

@pytest.fixture
def connector_with_data():
    conn = DataConnector()
    db = conn.get_connection()
    db.execute("""
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY,
            region TEXT,
            amount REAL,
            quantity INTEGER,
            notes TEXT
        )
    """)
    # Insert sample records
    records = [
        (1, "North", 150.50, 3, "Urgent"),
        (2, "South", 200.00, 5, None),
        (3, "North", 99.99, 1, "Standard"),
        (4, "East", 350.25, 7, None),
        (5, "North", 450.00, 10, "Bulk")
    ]
    db.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", records)
    conn.file_tables["dummy"] = ["sales"]
    return conn

def test_profile_table_numeric_and_categorical(connector_with_data):
    profile = DataProfiler.profile_table(connector_with_data, "sales")
    assert profile.table_name == "sales"
    assert profile.total_rows == 5
    assert profile.total_columns == 5
    
    col_map = {c.name: c for c in profile.columns}
    
    # Check numeric col: amount
    amount_col = col_map["amount"]
    assert amount_col.is_numeric is True
    assert amount_col.null_count == 0
    assert amount_col.min_val == pytest.approx(99.99)
    assert amount_col.max_val == pytest.approx(450.00)
    assert amount_col.mean_val is not None
    
    # Check categorical col: region
    region_col = col_map["region"]
    assert region_col.is_numeric is False
    assert region_col.unique_count == 3
    assert len(region_col.top_values) > 0
    assert region_col.top_values[0]["value"] == "North"
    assert region_col.top_values[0]["count"] == 3
    
    # Check nullable col: notes
    notes_col = col_map["notes"]
    assert notes_col.null_count == 2
    assert notes_col.null_percentage == 40.0

def test_profile_empty_table():
    conn = DataConnector()
    db = conn.get_connection()
    db.execute("CREATE TABLE empty_tbl (id INT, val TEXT)")
    conn.file_tables["dummy"] = ["empty_tbl"]
    
    profile = DataProfiler.profile_table(conn, "empty_tbl")
    assert profile.total_rows == 0
    assert profile.total_columns == 2

def test_format_profile_markdown(connector_with_data):
    profile = DataProfiler.profile_table(connector_with_data, "sales")
    md = DataProfiler.format_profile_markdown(profile)
    assert "Table Profile: `sales`" in md
    assert "amount" in md
    assert "North" in md
