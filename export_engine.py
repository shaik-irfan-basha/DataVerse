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
        """Converts columns and rows into a clean pandas DataFrame with native types."""
        if not columns:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=columns)

        # Ensure numeric values are preserved as true numeric types, not string representations
        for col in df.columns:
            if df[col].dtype == object:
                converted = pd.to_numeric(df[col], errors='coerce')
                if df[col].notna().any() and converted.notna().sum() == df[col].notna().sum():
                    has_leading_zero = any(
                        isinstance(v, str) and len(v) > 1 and v.startswith("0") and not v.startswith("0.")
                        for v in df[col] if pd.notna(v)
                    )
                    if not has_leading_zero:
                        df[col] = converted
        return df

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
        Applies bold styling, readable padding, auto-sizing for columns, freeze pane, and auto-filters.
        Returns the absolute path of the generated file.
        """
        df = cls._create_dataframe(columns, rows)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        safe_sheet_name = sheet_name[:31] if sheet_name else "Query Results"

        # Use openpyxl engine
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
            ws = writer.sheets[safe_sheet_name]

            # 1. Freeze header row
            ws.freeze_panes = "A2"

            # 2. Enable auto-filters on header row
            if ws.max_column > 0 and ws.max_row > 0:
                ws.auto_filter.ref = ws.dimensions

            # 3. Format header row
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            import openpyxl.utils

            header_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
            header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
            header_border = Border(
                top=Side(style="thin", color="CBD5E1"),
                bottom=Side(style="medium", color="94A3B8")
            )

            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.border = header_border
                cell.alignment = Alignment(vertical="center", horizontal="left")

            ws.row_dimensions[1].height = 24

            # 4. Auto-size columns based on longest cell/header value
            for col in ws.columns:
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                max_len = 0
                for cell in col:
                    if cell.value is not None:
                        val_str = str(cell.value)
                        lines = val_str.split("\n")
                        line_len = max(len(l) for l in lines) if lines else 0
                        if line_len > max_len:
                            max_len = line_len
                # Add padding (+4), with minimum width 12 and maximum width 60
                fitted_width = min(max(max_len + 4, 12), 60)
                ws.column_dimensions[col_letter].width = fitted_width

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
