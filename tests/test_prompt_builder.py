import pytest
from prompt_builder import build_universal_prompt

def test_build_universal_prompt():
    schema = "TABLE: users (id INTEGER, name TEXT)"
    sample = "1, Alice"
    question = "Who is Alice?"
    
    prompt = build_universal_prompt(question, schema, sample)
    
    # Assert critical pieces of context are included in the prompt
    assert schema in prompt
    assert sample in prompt
    assert question in prompt
    assert "SQLite" in prompt # Should instruct for SQLite dialect
    assert "no markdown, no code blocks" in prompt # Should ask for raw SQL
