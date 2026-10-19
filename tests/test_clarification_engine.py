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


def test_build_analysis_prompt_subjective_modifiers_and_entity_grounding():
    """
    Regression test: Verify that prompt instructions mandate:
    1. Detecting subjective descriptors ('good', 'important', 'best', etc.) as ambiguous.
    2. Enforcing target entity grounding (e.g., options must focus on products when asked about products).
    3. Strictly prohibiting topic drift (e.g., pivoting to 'Sales by region' for a product query).
    4. Scoping clarification history to prevent stale previous context from overriding new entities.
    5. Direct execution for baseline clear queries ('What are total sales by region?').
    """
    schema = "TABLE: sample_sales (product TEXT, sales INTEGER, region TEXT)"
    prompt = build_analysis_prompt("Show me the good products", schema)

    # Subjective modifiers guideline
    assert "SUBJECTIVE DESCRIPTORS" in prompt
    assert '"good"' in prompt
    assert '"important"' in prompt

    # Target entity grounding & anti-topic-drift
    assert "TARGET ENTITY GROUNDING" in prompt
    assert "STRICT PROHIBITION AGAINST TOPIC DRIFT" in prompt
    assert "Sales by region" in prompt

    # Clarification history scope
    assert "CLARIFICATION RESOLUTION & HISTORY SCOPE" in prompt
    assert "IGNORE the history completely" in prompt

    # Clear baseline aggregations
    assert "What are total sales by region?" in prompt


def test_query_analysis_good_products_schema_grounding():
    """
    Verify QueryAnalysis correctly models ambiguous 'Show me the good products'
    with options grounded strictly in the product entity and sales metric.
    """
    data = {
        "is_ambiguous": True,
        "reasoning": "The qualitative term 'good' does not specify a measurable ranking criterion (e.g., highest sales, sales above average, or volume).",
        "clarification_question": "How should good products be measured?",
        "options": [
            "Highest sales by product",
            "Lowest sales by product",
            "Products ranked by sales descending",
            "Products with sales above average"
        ]
    }
    analysis = QueryAnalysis(**data)
    assert analysis.is_ambiguous is True
    assert "good" in analysis.reasoning
    assert analysis.clarification_question == "How should good products be measured?"
    assert len(analysis.options) == 4
    # Ensure every option is grounded in the product entity
    for opt in analysis.options:
        assert "product" in opt.lower()
    assert analysis.sql_query is None


def test_query_analysis_important_sales():
    """
    Verify QueryAnalysis models ambiguous 'Show me the important sales'
    requiring clarification for undefined importance thresholds.
    """
    data = {
        "is_ambiguous": True,
        "reasoning": "The term 'important' is subjective without a defined sales threshold or criteria.",
        "clarification_question": "How should important sales be defined?",
        "options": [
            "Transactions with highest sales",
            "Sales above the average value",
            "Total sales by product",
            "Total sales by region"
        ]
    }
    analysis = QueryAnalysis(**data)
    assert analysis.is_ambiguous is True
    assert len(analysis.options) >= 2
    assert analysis.sql_query is None


def test_query_analysis_clear_baseline_sales_by_region():
    """
    Verify QueryAnalysis models unambiguous baseline 'What are total sales by region?'
    with is_ambiguous=False and direct SQLite aggregation.
    """
    data = {
        "is_ambiguous": False,
        "reasoning": "Straightforward grouping and aggregation of sales by region.",
        "sql_query": "SELECT region, SUM(sales) AS total_sales FROM sample_sales GROUP BY region ORDER BY total_sales DESC;"
    }
    analysis = QueryAnalysis(**data)
    assert analysis.is_ambiguous is False
    assert analysis.clarification_question is None
    assert analysis.options is None
    assert "SELECT region" in analysis.sql_query
    assert "SUM(sales)" in analysis.sql_query
