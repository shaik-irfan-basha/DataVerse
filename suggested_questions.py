"""
suggested_questions.py - Schema-Aware Suggested Questions Generator

Analyzes loaded dataset tables, column types, and data distributions to generate
intuitive, context-aware starter questions for users.
"""

from typing import List, Dict, Any, Optional
import sqlite3
import re
import logging
from data_connector import DataConnector

logger = logging.getLogger("dataverse.suggested")

class SuggestedQuestionsGenerator:
    """
    Generates tailored natural language queries based on loaded database schema.
    """

    @staticmethod
    def generate(connector: DataConnector, max_questions: int = 5) -> List[str]:
        """
        Inspects all loaded tables in the connector and generates 3-5 smart questions.
        """
        if not connector.is_loaded():
            return []
            
        questions = []
        with connector._lock:
            conn = connector.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [r[0] for r in cursor.fetchall()]
            
            if not tables:
                return []
                
            for table in tables:
                safe_table = connector._quote_identifier(table)
                cursor.execute(f"PRAGMA table_info({safe_table})")
                col_info = cursor.fetchall()  # [(cid, name, type, notnull, dflt_value, pk), ...]
                
                if not col_info:
                    continue
                    
                col_names = [c[1] for c in col_info]
                
                # Classify columns into numeric vs categorical candidates
                numeric_cols = []
                categorical_cols = []
                date_cols = []
                id_cols = []
                
                for c in col_info:
                    cname = c[1]
                    ctype = (c[2] or "").upper()
                    lower = cname.lower()
                    
                    is_id = lower == "id" or lower.endswith("_id") or lower.startswith("id_")
                    
                    if is_id:
                        id_cols.append(cname)
                    elif any(t in ctype for t in ["INT", "REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL"]):
                        numeric_cols.append(cname)
                    elif any(t in ctype for t in ["DATE", "TIME"]) or any(w in lower for w in ["date", "time", "year", "month"]):
                        date_cols.append(cname)
                    else:
                        categorical_cols.append(cname)
                
                # If no other numeric columns exist, fall back to id_cols
                if not numeric_cols and id_cols:
                    numeric_cols = id_cols.copy()
                    
                clean_table = table.replace("_", " ").title()
                
                # 1. Row count question
                questions.append(f"How many total records are in the {clean_table} table?")
                
                # 2. Aggregation question if numeric col exists
                if numeric_cols:
                    num_col = numeric_cols[0]
                    clean_num = num_col.replace("_", " ")
                    questions.append(f"What is the average {clean_num} in {clean_table}?")
                    
                # 3. Top records
                if numeric_cols:
                    num_col = numeric_cols[0]
                    clean_num = num_col.replace("_", " ")
                    questions.append(f"Show the top 5 records in {clean_table} with highest {clean_num}.")
                    
                # 4. Group by
                if numeric_cols and categorical_cols:
                    num_col = numeric_cols[0]
                    cat_col = categorical_cols[0]
                    questions.append(f"What is the total {num_col.replace('_', ' ')} grouped by {cat_col.replace('_', ' ')}?")
                    
                # 5. Distinct categories
                if categorical_cols:
                    cat_col = categorical_cols[0]
                    questions.append(f"List all distinct {cat_col.replace('_', ' ')} in {clean_table}.")

                if len(questions) >= max_questions * 2:
                    break
                    
        # Deduplicate while preserving order and limit to max_questions
        seen = set()
        unique_questions = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)
            if len(unique_questions) >= max_questions:
                break
                
        return unique_questions
