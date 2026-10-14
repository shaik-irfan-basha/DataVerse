"""
export_engine.py - Query Result Export Engine

Exports execution results into industry-standard data formats:
- CSV (RFC 4180 compliant)
- Excel (.xlsx) with styled headers
- JSON (records/split orient)
- Markdown Table & Clipboard TSV
"""

import os
import csv
import json
from typing import List, Tuple, Any, Dict, Optional
import pandas as pd
import logging

logger = logging.getLogger("dataverse.export")

class ExportEngine:
    """
    Exports structured query results into various file formats.
    """

    @staticmethod
    def _create_dataframe(columns: List[str], rows: List[Tuple[Any, ...]]) -> pd.DataFrame:
        """Converts columns and rows into a clean pandas DataFrame."""
        if not columns:
            return pd.DataFrame()
        return pd.DataFrame(rows, columns=columns)

    @classmethod
    def export_to_csv(cls, columns: List[str], rows: List[Tuple[Any, ...]], file_path: str) -> str:
        """
        Exports results to a CSV file.
        Returns the absolute path of the generated file.
        """
        df = cls._create_dataframe(columns, rows)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
        logger.info(f"Exported {len(df)} rows to CSV: {file_path}")
        return os.path.abspath(file_path)

    @classmethod
    def export_to_excel(cls, 
                        columns: List[str], 
                        rows: List[Tuple[Any, ...]], 
                        file_path: str, 
                        sheet_name: str = "Query Results") -> str:
        """
        Exports results to an Excel workbook (.xlsx).
        Returns the absolute path of the generated file.
        """
        df = cls._create_dataframe(columns, rows)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        
        # Use openpyxl engine
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            
        logger.info(f"Exported {len(df)} rows to Excel: {file_path}")
        return os.path.abspath(file_path)

    @classmethod
    def export_to_json(cls, 
                       columns: List[str], 
                       rows: List[Tuple[Any, ...]], 
                       file_path: str, 
                       indent: int = 2) -> str:
        """
        Exports results to a JSON file.
        Returns the absolute path of the generated file.
        """
        df = cls._create_dataframe(columns, rows)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        records = df.to_dict(orient="records")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=indent, default=str)
        logger.info(f"Exported {len(df)} rows to JSON: {file_path}")
        return os.path.abspath(file_path)

    @classmethod
    def to_markdown(cls, columns: List[str], rows: List[Tuple[Any, ...]], max_rows: int = 50) -> str:
        """
        Formats results as a Markdown table.
        """
        if not columns:
            return "_No columns available._"
        if not rows:
            header = "| " + " | ".join(columns) + " |"
            sep = "| " + " | ".join(["---"] * len(columns)) + " |"
            return f"{header}\n{sep}\n|_Empty result set_|"
            
        df = cls._create_dataframe(columns, rows[:max_rows])
        return df.to_markdown(index=False)

    @classmethod
    def to_tsv(cls, columns: List[str], rows: List[Tuple[Any, ...]]) -> str:
        """
        Formats results as tab-separated values (TSV) suitable for pasting into spreadsheets.
        """
        if not columns:
            return ""
        lines = ["\t".join(columns)]
        for r in rows:
            lines.append("\t".join(str(val) if val is not None else "" for val in r))
        return "\n".join(lines)
