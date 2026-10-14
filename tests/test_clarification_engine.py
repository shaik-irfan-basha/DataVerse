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
