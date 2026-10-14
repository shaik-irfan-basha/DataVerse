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
"""

    if clarification_history:
        prompt += f"""
CLARIFICATION HISTORY (Context):
{clarification_history}
"""

    prompt += f"""
INSTRUCTIONS:
1. Analyze the USER QUESTION against the DATABASE SCHEMA.
2. If the question contains subjective words (like 'best', 'top', 'most active', 'recent') and the schema provides multiple ways to calculate it, IT IS AMBIGUOUS. 
   - Set `is_ambiguous` to true.
   - Provide a `clarification_question`.
   - Provide 2-4 concrete `options` (e.g., 'Total Revenue', 'Order Count').
3. If the question is clear, or if the CLARIFICATION HISTORY resolves the ambiguity:
   - Set `is_ambiguous` to false.
   - Generate the final SQLite query in `sql_query`.
4. You MUST output a valid JSON object that strictly matches the following JSON Schema:

{schema_json}

Output ONLY the JSON object. No markdown formatting, no explanations outside the JSON.
"""
    return prompt
