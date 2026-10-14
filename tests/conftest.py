import pytest
import os
import csv
import json
import sqlite3
import pandas as pd
from typing import Dict, Any

@pytest.fixture
def mock_csv_file(tmp_path):
    """Provides a path to a temporary CSV file with sample data."""
    csv_file = tmp_path / "test_data.csv"
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'score'])
        writer.writerow([1, 'Alice', 95])
        writer.writerow([2, 'Bob', 85])
    return str(csv_file)

@pytest.fixture
def mock_json_file(tmp_path):
    """Provides a path to a temporary JSON file with sample data."""
    json_file = tmp_path / "test_data.json"
    data = [
        {"item": "Laptop", "price": 1200},
        {"item": "Mouse", "price": 25}
    ]
    with open(json_file, 'w') as f:
        json.dump(data, f)
    return str(json_file)

@pytest.fixture
def mock_excel_file(tmp_path):
    """Provides a path to a temporary Excel file with multiple sheets."""
    excel_file = tmp_path / "test_data.xlsx"
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        pd.DataFrame({'a': [1, 2], 'b': [3, 4]}).to_excel(writer, sheet_name='Sheet1', index=False)
        pd.DataFrame({'x': ['foo'], 'y': ['bar']}).to_excel(writer, sheet_name='Sheet2', index=False)
    return str(excel_file)

@pytest.fixture
def mock_sqlite_file(tmp_path):
    """Provides a path to a temporary external SQLite database with sample data."""
    db_file = tmp_path / "external_data.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER, username TEXT)")
    cursor.execute("INSERT INTO users VALUES (1, 'admin')")
    cursor.execute("INSERT INTO users VALUES (2, 'guest')")
    
    cursor.execute("CREATE TABLE settings (key TEXT, value TEXT)")
    cursor.execute("INSERT INTO settings VALUES ('theme', 'dark')")
    conn.commit()
    conn.close()
    return str(db_file)

@pytest.fixture
def mock_llm_client(monkeypatch):
    """Mocks the LLMClient so no real network requests are made."""
    class MockLLM:
        def __init__(self, provider="mock", model="mock-model"):
            self.provider = provider
            self.model = model
            self.last_prompt = None
            
        def generate_json(self, prompt: str) -> Dict[str, Any]:
            self.last_prompt = prompt
            # Standard successful response
            return {
                "is_ambiguous": False,
                "sql_query": "SELECT * FROM test_table;",
                "reasoning": "Mocked clear reasoning",
                "clarification_question": "",
                "options": []
            }
            
        def generate_sql(self, prompt: str) -> str:
            self.last_prompt = prompt
            return "SELECT * FROM test_table;"
            
    # Mock the class in llm_client module
    import llm_client
    monkeypatch.setattr(llm_client, "LLMClient", MockLLM)
    return MockLLM
