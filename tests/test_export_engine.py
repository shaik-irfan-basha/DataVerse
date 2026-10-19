import pytest
import os
import tempfile
import json
import pandas as pd
from export_engine import ExportEngine

@pytest.fixture
def sample_data():
    columns = ["id", "product", "price", "in_stock"]
    rows = [
        (1, "Laptop", 999.99, True),
        (2, "Mouse", 25.50, True),
        (3, "Keyboard", 75.00, False),
    ]
    return columns, rows

def test_export_to_csv(sample_data):
    columns, rows = sample_data
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    try:
        ExportEngine.export_to_csv(columns, rows, path)
        assert os.path.exists(path)
        df = pd.read_csv(path)
        assert len(df) == 3
        assert list(df.columns) == columns
        assert df["product"].tolist() == ["Laptop", "Mouse", "Keyboard"]
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_export_to_excel(sample_data):
    columns, rows = sample_data
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        ExportEngine.export_to_excel(columns, rows, path)
        assert os.path.exists(path)
        df = pd.read_excel(path)
        assert len(df) == 3
        assert list(df.columns) == columns
        assert df["product"].tolist() == ["Laptop", "Mouse", "Keyboard"]

        # Open with openpyxl to inspect styles and metadata
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active

        # 1. Verify freeze panes on row 1
        assert ws.freeze_panes == "A2"

        # 2. Verify auto filter
        assert ws.auto_filter.ref is not None

        # 3. Verify bold headers
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=1, column=col_idx)
            assert cell.font.bold is True

        # 4. Verify column auto-sizing gives adequate width
        for col in ws.columns:
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            width = ws.column_dimensions[col_letter].width
            assert width >= 12.0
            assert width <= 60.0

        # 5. Verify real numeric cells (price should be numeric, not string)
        # Price is column 3 (C)
        price_cell = ws["C2"]
        assert price_cell.data_type == "n"
        assert price_cell.value == 999.99
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_export_to_excel_long_headers_and_numeric_strings():
    """Verify long headers are not cramped and numeric strings convert to true numbers."""
    columns = ["Transaction_Identification_Number", "Customer_Name", "Total_Amount"]
    rows = [
        ("1001", "Acme Corporation", "2450.50"),
        ("1002", "Globex Global Industries", "180.00")
    ]
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        ExportEngine.export_to_excel(columns, rows, path)
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active

        # Column A header is 33 chars long -> width should be >= 37
        width_a = ws.column_dimensions["A"].width
        assert width_a >= len("Transaction_Identification_Number")

        # Amount column should be true numeric cell 'n'
        amount_cell = ws["C2"]
        assert amount_cell.data_type == "n"
        assert amount_cell.value == 2450.50
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_export_to_json(sample_data):
    columns, rows = sample_data
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ExportEngine.export_to_json(columns, rows, path)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 3
        assert data[0]["product"] == "Laptop"
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_to_markdown(sample_data):
    columns, rows = sample_data
    md = ExportEngine.to_markdown(columns, rows)
    assert "product" in md
    assert "price" in md
    assert "Laptop" in md

def test_to_tsv(sample_data):
    columns, rows = sample_data
    tsv = ExportEngine.to_tsv(columns, rows)
    assert "id\tproduct\tprice\tin_stock" in tsv
    assert "1\tLaptop\t999.99\tTrue" in tsv
