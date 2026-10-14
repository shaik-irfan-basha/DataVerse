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
