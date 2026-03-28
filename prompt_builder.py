"""
prompt_builder.py - Build prompts for LLM to generate SQL queries

This module constructs clear, well-formatted prompts that instruct
the LLM to act as an SQL expert and generate SQL from natural language.
"""


def build_sql_prompt(question: str, table_schema: list, table_name: str = "table") -> str:
    """
    Build a prompt for the LLM to generate SQL from natural language.
    
    The prompt is designed to:
    1. Clearly establish the LLM's role as an SQL expert
    2. Provide the table structure (column names)
    3. Present the natural language question
    4. Request ONLY the SQL query (no explanations)
    
    Args:
        question: The natural language question to convert to SQL
        table_schema: List of column names in the table
        table_name: Name of the table (default: "table")
    
    Returns:
        Formatted prompt string ready to send to the LLM
    """
    # Format column names as a comma-separated list
    columns_str = ", ".join(table_schema)
    
    # Build the prompt with clear instructions
    prompt = f"""You are an expert SQL query generator. Your task is to convert natural language questions into valid SQL queries.

TABLE INFORMATION:
- Table name: {table_name}
- Columns: {columns_str}

QUESTION:
{question}

INSTRUCTIONS:
1. Generate a valid SQL SELECT query that answers the question
2. Use only the columns provided above
3. Return ONLY the SQL query, nothing else
4. Do not include any explanations or comments
5. Do not use markdown code blocks

SQL QUERY:"""
    
    return prompt


def build_simple_prompt(question: str, table_schema: list) -> str:
    """
    Build a simpler, more concise prompt for SQL generation.
    
    This is an alternative prompt format that may work better
    with some LLM models.
    
    Args:
        question: The natural language question
        table_schema: List of column names
    
    Returns:
        Simple formatted prompt string
    """
    columns_str = ", ".join(table_schema)
    
    prompt = f"""Convert this question to SQL.

Table columns: {columns_str}

Question: {question}

SQL:"""
    
    return prompt


# =============================================================================
# MAIN - For testing this module independently
# =============================================================================

if __name__ == "__main__":
    # Test the prompt builder
    print("=" * 60)
    print("Testing prompt_builder.py")
    print("=" * 60)
    
    # Example data
    test_question = "What is the total population of California?"
    test_schema = ["state", "population", "area", "capital"]
    test_table = "states"
    
    # Build and display the prompt
    prompt = build_sql_prompt(test_question, test_schema, test_table)
    
    print("\nGenerated Prompt:")
    print("-" * 40)
    print(prompt)
    print("-" * 40)
