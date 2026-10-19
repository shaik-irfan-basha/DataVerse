import pytest
from clarification_engine import build_analysis_prompt, QueryAnalysis
import json

def test_build_analysis_prompt():
    schema = "TABLE: sales (amount REAL)"
    sample = "100.0"
    question = "Who is the best customer?"
    history = "User clarified: by amount"

    prompt = build_analysis_prompt(question, schema, sample, history)

    # Check that inputs are injected
    assert schema in prompt
    assert question in prompt
    assert history in prompt

    # Check that the Pydantic JSON schema is injected
    assert "JSON" in prompt

    # Generate the schema from Pydantic to ensure it matches what should be in the prompt
    pydantic_schema = json.dumps(QueryAnalysis.model_json_schema(), indent=2)
    assert "is_ambiguous" in pydantic_schema
    assert "clarification_question" in pydantic_schema
    assert "reasoning" in pydantic_schema


def test_build_analysis_prompt_grounding_and_preview_rules():
    """Verify that instructions explicitly handle clear row previews, genuine ambiguity, and nonexistent columns."""
    schema = "TABLE: sample_sales (product TEXT, sales INTEGER, region TEXT)"
    prompt = build_analysis_prompt("Show the top 5 rows", schema)

    # Check key grounding & clear query instruction guidelines
    assert "CLEAR REQUESTS" in prompt
    assert "Show the top 5 rows" in prompt
    assert "GENUINE AMBIGUITY" in prompt
    assert "SCHEMA GROUNDING" in prompt
    assert "Never invent, hallucinate, or assume columns" in prompt


def test_query_analysis_pydantic_models():
    """Verify QueryAnalysis validates both ambiguous and unambiguous structures."""
    # 1. Clear query
    clear_data = {
        "is_ambiguous": False,
        "reasoning": "Simple row limit query",
        "sql_query": "SELECT * FROM sample_sales LIMIT 5;"
    }
    obj_clear = QueryAnalysis(**clear_data)
    assert obj_clear.is_ambiguous is False
    assert obj_clear.sql_query == "SELECT * FROM sample_sales LIMIT 5;"

    # 2. Ambiguous query with options
    ambig_data = {
        "is_ambiguous": True,
        "reasoning": "Performance can be measured in multiple ways",
        "clarification_question": "How should product performance be measured?",
        "options": ["Total Sales (SUM)", "Average Sales (AVG)"]
    }
    obj_ambig = QueryAnalysis(**ambig_data)
    assert obj_ambig.is_ambiguous is True
    assert len(obj_ambig.options) == 2
    assert "Total Sales" in obj_ambig.options[0]
