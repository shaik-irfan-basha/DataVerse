"""
clarification_engine.py - Ambiguity Detection & Clarification

Uses Pydantic structured schemas to force the LLM to analyze a query
for ambiguity before generating SQL. If ambiguous, it returns a
clarification question and multiple-choice options.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
import json


class QueryAnalysis(BaseModel):
    """Structured output schema for the LLM to analyze the user's intent."""
    is_ambiguous: bool = Field(
        description="True if the question uses subjective words (e.g., 'best', 'top', 'recent', 'active') and could have multiple interpretations based on the schema."
    )
    reasoning: str = Field(
        description="Short explanation of why the question is or isn't ambiguous."
    )
    clarification_question: Optional[str] = Field(
        None,
        description="If ambiguous, the question to ask the user to clarify their intent."
    )
    options: Optional[List[str]] = Field(
        None,
        description="If ambiguous, provide 2 to 4 concrete options (e.g., ['By Revenue', 'By Number of Orders'])."
    )
    sql_query: Optional[str] = Field(
        None,
        description="If NOT ambiguous (is_ambiguous=false), generate the final valid SQLite SELECT query here."
    )


def build_analysis_prompt(
    question: str,
    schema_string: str,
    sample_data: str = "",
    clarification_history: str = ""
) -> str:
    """
    Build a prompt that forces the LLM to output a JSON object matching
    the QueryAnalysis Pydantic schema.
    """

    schema_json = json.dumps(QueryAnalysis.model_json_schema(), indent=2)

    history_block = f"\nCLARIFICATION HISTORY (Context):\n{clarification_history}\n" if clarification_history else ""

    prompt = f"""You are an expert Data Analyst and Database Architect.
Your job is to translate a user's natural language question into a SQLite SQL query.

DATABASE SCHEMA:
{schema_string}
"""

    if sample_data:
        prompt += f"\n{sample_data}\n"

    prompt += f"""
USER QUESTION:
{question}
{history_block}
INSTRUCTIONS:
1. Analyze the USER QUESTION against the DATABASE SCHEMA and sample data.

2. CLEAR REQUESTS (EXECUTE DIRECTLY WITHOUT CLARIFICATION):
   - Row-limit, preview, and pagination requests such as "Show the top 5 rows", "Show the first 5 rows", "Show 5 rows", "Display 10 rows", or "Show all data" are CLEAR. Do NOT ask for clarification.
     Set `is_ambiguous` to false and generate `SELECT * FROM <table> LIMIT 5;` (or the requested limit using the loaded table).
   - Unambiguous aggregations, groupings, or filters where intent and columns are straightforward (e.g., "What are the average sales by region?", "Total sales by product", "List products in South region") are CLEAR.
     Set `is_ambiguous` to false and generate the SQLite SELECT query in `sql_query`.

3. GENUINE AMBIGUITY (WHEN TO CLARIFY):
   - When a question uses subjective or comparative words (e.g., "best", "best-performing", "top performing", "most active", "worst") without a specified calculation formula, and the schema supports multiple possible metrics or dimensions:
     - Set `is_ambiguous` to true.
     - Set `reasoning` to explain why the question is ambiguous.
     - Set `clarification_question` to ask a concise follow-up question.
     - Set `options` to 2 to 4 concrete, actionable interpretations grounded strictly in existing schema columns.

4. SCHEMA GROUNDING & NONEXISTENT COLUMNS/TABLES:
   - Base all queries strictly on existing table names and column names in the DATABASE SCHEMA.
   - Never invent, hallucinate, or assume columns, tables, or metrics not in the schema.
   - If the question asks for a column or entity that does NOT exist in the schema (e.g., asking for 'salary', 'profit', 'employee'):
     - Set `is_ambiguous` to true.
     - Set `reasoning` to explain that the requested column does not exist in the dataset.
     - Set `clarification_question` to explain that the column does not exist in the database, list the available columns, and ask how the user would like to proceed.
     - Set `options` to 2 to 4 valid alternative queries using existing schema columns.

5. CLARIFICATION RESOLUTION:
   - If CLARIFICATION HISTORY is provided and resolves the ambiguity, or specifies the user's chosen interpretation:
     - Set `is_ambiguous` to false.
     - Generate the final SQLite query in `sql_query` incorporating the user's choice.

6. OUTPUT FORMAT:
You MUST output a valid JSON object that strictly matches the following JSON Schema:

{schema_json}

Output ONLY the JSON object. No markdown formatting, no explanations outside the JSON.
"""
    return prompt
