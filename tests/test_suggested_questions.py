import pytest
from data_connector import DataConnector
from suggested_questions import SuggestedQuestionsGenerator

def test_suggested_questions_generation():
    conn = DataConnector()
    db = conn.get_connection()
    db.execute("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            city TEXT,
            total_spend REAL,
            signup_date TEXT
        )
    """)
    conn.file_tables["dummy"] = ["customers"]
    
    questions = SuggestedQuestionsGenerator.generate(conn, max_questions=5)
    assert len(questions) > 0
    assert any("customers" in q.lower() or "records" in q.lower() for q in questions)
    assert any("total spend" in q.lower() or "spend" in q.lower() for q in questions)

def test_suggested_questions_unloaded_connector():
    conn = DataConnector()
    questions = SuggestedQuestionsGenerator.generate(conn)
    assert questions == []
