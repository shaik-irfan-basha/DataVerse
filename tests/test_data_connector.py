import pytest
from data_connector import DataConnector

def test_load_csv_creates_table(mock_csv_file):
    dc = DataConnector()
    tables = dc.load_file(mock_csv_file)
    assert len(tables) == 1
    assert "test_data" in tables[0]
    assert dc.file_type == "CSV"
    
    # Check row count
    assert dc.get_row_count(tables[0]) == 2

def test_load_json_creates_table(mock_json_file):
    dc = DataConnector()
    tables = dc.load_file(mock_json_file)
    assert len(tables) == 1
    assert "test_data" in tables[0]
    assert dc.file_type == "JSON"
    assert dc.get_row_count(tables[0]) == 2

def test_load_excel_creates_multiple_tables(mock_excel_file):
    dc = DataConnector()
    tables = dc.load_file(mock_excel_file)
    assert len(tables) == 2
    
    # Check table names include sheet names
    assert any("sheet1" in t.lower() for t in tables)
    assert any("sheet2" in t.lower() for t in tables)
    assert dc.file_type == "Excel"
    
    # Verify rows across sheets
    total_rows = sum(dc.get_row_count(t) for t in tables)
    assert total_rows == 3 # sheet1 has 2 rows, sheet2 has 1

def test_load_sqlite_creates_tables(mock_sqlite_file):
    dc = DataConnector()
    tables = dc.load_file(mock_sqlite_file)
    assert len(tables) == 2
    assert dc.file_type == "SQLite"
    
    # external_data_users, external_data_settings
    users_table = next(t for t in tables if "users" in t)
    settings_table = next(t for t in tables if "settings" in t)
    
    assert dc.get_row_count(users_table) == 2
    assert dc.get_row_count(settings_table) == 1

def test_get_schema(mock_csv_file):
    dc = DataConnector()
    tables = dc.load_file(mock_csv_file)
    
    schema = dc.get_schema()
    assert tables[0] in schema
    
    columns = schema[tables[0]]
    col_names = [c["name"] for c in columns]
    assert "id" in col_names
    assert "name" in col_names
    assert "score" in col_names

def test_get_schema_string(mock_csv_file):
    dc = DataConnector()
    dc.load_file(mock_csv_file)
    schema_str = dc.get_schema_string()
    
    assert "TABLE:" in schema_str
    assert "id INTEGER" in schema_str or "id REAL" in schema_str or "id BIGINT" in schema_str # Pandas might infer bigint
    assert "name TEXT" in schema_str
