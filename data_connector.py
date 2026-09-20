"""
data_connector.py - Universal Data Connector

Loads any dataset (CSV, Excel, JSON, SQLite, Documents) into a SINGLE in-memory SQLite
database and extracts schema information for LLM prompt building. Supports multiple files.
"""

import os
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional
import re
import threading

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


SUPPORTED_EXTENSIONS = {
    ".csv": "CSV",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".json": "JSON",
    ".db": "SQLite",
    ".sqlite": "SQLite",
    ".sqlite3": "SQLite",
    ".pdf": "Document",
    ".docx": "Document",
    ".doc": "Document",
    ".pptx": "Document",
    ".ppt": "Document",
}


class DataConnector:
    """
    Universal data connector (Multi-file support).
    Loads multiple files into a shared in-memory SQLite database.
    """
    
    def __init__(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.file_tables: Dict[str, List[str]] = {}  # filepath -> list of table names
        self.file_type: str = ""  # Most recently loaded file type (e.g., "CSV", "Excel")
        self._lock = threading.Lock()  # Thread safety for shared connection
        
    @staticmethod
    def _quote_identifier(name: str) -> str:
        """Safely quote a SQLite identifier to prevent SQL injection."""
        return '"' + name.replace('"', '""') + '"'

    def _get_unique_table_name(self, base_name: str) -> str:
        """Ensure the table name is unique across the shared database."""
        name = re.sub(r'\W|^(?=\d)', '_', base_name).lower()
        
        # Check existing tables
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing = [row[0] for row in cursor.fetchall()]
        
        if name not in existing:
            return name
            
        counter = 1
        while f"{name}_{counter}" in existing:
            counter += 1
        return f"{name}_{counter}"

    def load_file(self, file_path: str) -> List[str]:
        """Loads a file and returns the list of table names created for it."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: '{ext}'")
        
        file_type = SUPPORTED_EXTENSIONS[ext]
        self.file_type = file_type
        added_tables = []
        
        print(f"Loading {file_type} file: {file_path}")
        
        # Route to loader
        if file_type == "CSV":
            added_tables = self._load_csv(file_path)
        elif file_type == "Excel":
            added_tables = self._load_excel(file_path)
        elif file_type == "JSON":
            added_tables = self._load_json(file_path)
        elif file_type == "SQLite":
            added_tables = self._load_sqlite(file_path)
        elif file_type == "Document":
            added_tables = self._load_document(file_path, ext)
            
        self.file_tables[file_path] = added_tables
        return added_tables

    def _load_csv(self, file_path: str) -> List[str]:
        if not HAS_PANDAS: raise ImportError("pandas required")
        table_name = self._get_unique_table_name(Path(file_path).stem)
        df = pd.read_csv(file_path)
        df.to_sql(table_name, self.connection, index=False, if_exists="replace")
        return [table_name]
    
    def _load_excel(self, file_path: str) -> List[str]:
        if not HAS_PANDAS: raise ImportError("pandas required")
        sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
        added = []
        for sheet_name, df in sheets.items():
            table_name = self._get_unique_table_name(f"{Path(file_path).stem}_{sheet_name}")
            df.to_sql(table_name, self.connection, index=False, if_exists="replace")
            added.append(table_name)
        return added
    
    def _load_json(self, file_path: str) -> List[str]:
        if not HAS_PANDAS: raise ImportError("pandas required")
        table_name = self._get_unique_table_name(Path(file_path).stem)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            list_keys = [k for k, v in data.items() if isinstance(v, list)]
            if list_keys:
                for key in list_keys:
                    if len(data[key]) > 0 and isinstance(data[key][0], dict):
                        df = pd.DataFrame(data[key])
                        table_name = self._get_unique_table_name(f"{Path(file_path).stem}_{key}")
                        break
                else:
                    df = pd.DataFrame(data)
            else:
                df = pd.DataFrame([data])
        else:
            raise ValueError("Unsupported JSON structure.")
            
        df.to_sql(table_name, self.connection, index=False, if_exists="replace")
        return [table_name]
        
    def _load_document(self, file_path: str, ext: str) -> List[str]:
        table_name = self._get_unique_table_name(Path(file_path).stem)
        data = []
        if ext == ".pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                for i, page in enumerate(doc):
                    text = page.get_text()
                    if text and text.strip(): data.append({"page": i+1, "content": text.strip()})
            except ImportError:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for i, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text and text.strip(): data.append({"page": i+1, "content": text.strip()})
        elif ext in [".docx", ".doc"]:
            import docx
            doc = docx.Document(file_path)
            for i, para in enumerate(doc.paragraphs):
                if para.text.strip(): data.append({"paragraph": i+1, "content": para.text})
        elif ext in [".pptx", ".ppt"]:
            from pptx import Presentation
            prs = Presentation(file_path)
            for i, slide in enumerate(prs.slides):
                text = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
                if text: data.append({"slide": i+1, "content": "\n".join(text)})
                
        if not data:
            if ext == ".pdf":
                raise ValueError("No text extracted. Scanned PDFs require OCR which is not supported.")
            raise ValueError(f"No readable text extracted from {ext.upper()}.")
            
        df = pd.DataFrame(data)
        df.to_sql(table_name, self.connection, index=False, if_exists="replace")
        return [table_name]

    def _load_sqlite(self, file_path: str) -> List[str]:
        """Read tables from external SQLite and copy them to in-memory DB."""
        temp_conn = sqlite3.connect(file_path)
        cursor = temp_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        
        added = []
        for t in tables:
            df = pd.read_sql(f"SELECT * FROM {self._quote_identifier(t)}", temp_conn)
            table_name = self._get_unique_table_name(f"{Path(file_path).stem}_{t}")
            df.to_sql(table_name, self.connection, index=False, if_exists="replace")
            added.append(table_name)
        temp_conn.close()
        return added

    def get_schema(self, active_tables: List[str] = None) -> Dict[str, List[Dict]]:
        """Returns schema for active tables (or all if none specified)."""
        cursor = self.connection.cursor()
        if active_tables is None:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            active_tables = [r[0] for r in cursor.fetchall()]
            
        schema = {}
        for table in active_tables:
            cursor.execute(f"PRAGMA table_info({self._quote_identifier(table)});")
            columns = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]
            schema[table] = columns
        return schema

    def get_schema_string(self, active_tables: List[str] = None) -> str:
        schema = self.get_schema(active_tables)
        lines = []
        for table, cols in schema.items():
            col_strs = [f"{c['name']} {c['type']}" for c in cols]
            lines.append(f"TABLE: {table} ({', '.join(col_strs)})")
        return "\n".join(lines)

    def get_sample_data_string(self, max_rows: int = 3, active_tables: List[str] = None) -> str:
        schema = self.get_schema(active_tables)
        cursor = self.connection.cursor()
        lines = []
        for table in schema.keys():
            cursor.execute(f"SELECT * FROM {self._quote_identifier(table)} LIMIT {max_rows};")
            rows = cursor.fetchall()
            if not rows: continue
            
            col_names = [c["name"] for c in schema[table]]
            lines.append(f"\nSAMPLE DATA for {table}:")
            lines.append("| " + " | ".join(col_names) + " |")
            for r in rows:
                lines.append("| " + " | ".join(str(val) for val in r) + " |")
        return "\n".join(lines)
        
    def get_row_count(self, table_name: str) -> int:
        cursor = self.connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self._quote_identifier(table_name)}")
        return cursor.fetchone()[0]

    def get_connection(self):
        return self.connection
        
    def is_loaded(self) -> bool:
        return len(self.file_tables) > 0

    @staticmethod
    def get_filetypes() -> list:
        return [
            ("All Supported", "*.csv;*.xlsx;*.xls;*.json;*.db;*.sqlite;*.sqlite3;*.pdf;*.docx;*.doc;*.pptx;*.ppt"),
            ("Data Files", "*.csv;*.xlsx;*.xls;*.json"),
            ("SQLite Databases", "*.db;*.sqlite;*.sqlite3"),
            ("Documents", "*.pdf;*.docx;*.doc;*.pptx;*.ppt"),
            ("All Files", "*.*"),
        ]
