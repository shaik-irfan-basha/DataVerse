"""
data_loader.py - WikiSQL Data Loader

Phase 1: Data preparation and preprocessing
- Load JSONL files (train/dev/test)
- Parse SQL structure (sel, conds, agg format)
- Extract table schemas from table data
- Convert to standardized format

Dataset Structure (WikiSQL JSONL format):
    phase: integer
    table_id: string (e.g., "1-10015132-11")
    question: string (natural language question)
    sql: dictionary with:
        sel: integer (selected column index)
        conds: list of conditions [col_idx, op_idx, value]
        agg: integer (0=none, 1=MAX, 2=MIN, 3=COUNT, 4=SUM, 5=AVG)
    table: dictionary with:
        header: list of column names
        types: list of column types ('text' or 'real')
        rows: list of table data rows

Data Source: Salesforce WikiSQL dataset
Download: https://github.com/salesforce/WikiSQL
"""

import json
import os
import tarfile
import urllib.request
from pathlib import Path
from typing import List, Dict, Optional


# =============================================================================
# CONSTANTS
# =============================================================================

# Aggregation operators (indexed by 'agg' value)
AGG_OPS = ['', 'MAX', 'MIN', 'COUNT', 'SUM', 'AVG']

# Condition operators (indexed by operator value in conds)
COND_OPS = ['=', '>', '<', '>=', '<=', '!=']

# Dataset download URL (Salesforce WikiSQL)
WIKISQL_URL = "https://github.com/salesforce/WikiSQL/raw/master/data.tar.bz2"

# Dataset splits
SPLITS = ['train', 'dev', 'test']


# =============================================================================
# WIKISQL DATA LOADER CLASS
# =============================================================================

class WikiSQLLoader:
    """
    WikiSQL Dataset Loader
    
    Downloads and parses the WikiSQL dataset from Salesforce.
    Handles all 3 splits (train/dev/test) with proper SQL structure parsing.
    
    Attributes:
        data_dir: Directory to store downloaded data
        examples: Loaded examples dictionary by split
        tables: Loaded tables dictionary
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize the WikiSQL loader.
        
        Args:
            data_dir: Directory to store downloaded JSONL files
        """
        self.data_dir = data_dir or os.path.join(os.getcwd(), "data")
        self.examples = {}
        self.tables = {}
        
        # Create data directory
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"WikiSQL Loader initialized")
        print(f"  Data directory: {self.data_dir}")
    
    # -------------------------------------------------------------------------
    # DOWNLOAD METHODS
    # -------------------------------------------------------------------------
    
    def download_dataset(self) -> bool:
        """
        Download the WikiSQL dataset if not already present.
        
        Returns:
            True if dataset is ready, False otherwise
        """
        train_path = os.path.join(self.data_dir, "train.jsonl")
        
        # Check if already downloaded
        if os.path.exists(train_path):
            print("Dataset already downloaded.")
            return True
        
        archive_path = os.path.join(self.data_dir, "data.tar.bz2")
        
        try:
            # Download the archive
            print(f"Downloading WikiSQL dataset from Salesforce...")
            print(f"  URL: {WIKISQL_URL}")
            
            urllib.request.urlretrieve(WIKISQL_URL, archive_path)
            print("  Download complete!")
            
            # Extract the archive
            print("  Extracting files...")
            with tarfile.open(archive_path, 'r:bz2') as tar:
                tar.extractall(self.data_dir)
            
            # Move files from data/ subdirectory to data_dir
            extracted_dir = os.path.join(self.data_dir, "data")
            if os.path.exists(extracted_dir):
                for filename in os.listdir(extracted_dir):
                    src = os.path.join(extracted_dir, filename)
                    dst = os.path.join(self.data_dir, filename)
                    if not os.path.exists(dst):
                        os.rename(src, dst)
                os.rmdir(extracted_dir)
            
            # Clean up archive
            os.remove(archive_path)
            
            print("  Extraction complete!")
            return True
            
        except Exception as e:
            print(f"Download failed: {e}")
            return False
    
    # -------------------------------------------------------------------------
    # DATA LOADING METHODS
    # -------------------------------------------------------------------------
    
    def load_tables(self, split: str = "train") -> Dict:
        """
        Load tables file for a split.
        
        Args:
            split: Dataset split (train, dev, test)
        
        Returns:
            Dictionary of table_id -> table_data
        """
        tables_file = os.path.join(self.data_dir, f"{split}.tables.jsonl")
        
        if not os.path.exists(tables_file):
            self.download_dataset()
        
        if split in self.tables:
            return self.tables[split]
        
        tables = {}
        print(f"Loading {split} tables...")
        
        with open(tables_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    table = json.loads(line)
                    tables[table['id']] = table
        
        print(f"  Loaded {len(tables)} tables")
        self.tables[split] = tables
        return tables
    
    def load_jsonl(self, split: str = "train") -> List[Dict]:
        """
        Load a JSONL file and parse all examples.
        
        Args:
            split: Dataset split to load (train, dev, test)
        
        Returns:
            List of parsed example dictionaries
        """
        if split in self.examples:
            return self.examples[split]
        
        file_path = os.path.join(self.data_dir, f"{split}.jsonl")
        
        if not os.path.exists(file_path):
            self.download_dataset()
        
        # Load tables first
        tables = self.load_tables(split)
        
        examples = []
        print(f"Loading {split} examples...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    raw = json.loads(line)
                    
                    # Get table data
                    table_id = raw.get("table_id", "")
                    table_data = tables.get(table_id, {})
                    
                    # Parse example with table data
                    parsed = self.parse_example(raw, table_data)
                    examples.append(parsed)
                    
                except json.JSONDecodeError as e:
                    print(f"  JSON error at line {line_num + 1}: {e}")
                except Exception as e:
                    print(f"  Parse error at line {line_num + 1}: {e}")
        
        print(f"  Loaded {len(examples)} examples")
        self.examples[split] = examples
        return examples
    
    # -------------------------------------------------------------------------
    # PARSING METHODS
    # -------------------------------------------------------------------------
    
    def parse_example(self, raw: Dict, table_data: Dict) -> Dict:
        """
        Parse a raw JSONL example into a structured format.
        
        Args:
            raw: Raw dictionary from JSONL line
            table_data: Table data from tables file
        
        Returns:
            Structured example with:
                - question: Natural language question
                - table_id: Table identifier
                - table_schema: List of column names
                - table_types: List of column types
                - table_rows: List of table data rows
                - sql: Original SQL structure {sel, conds, agg}
                - sql_readable: Human-readable SQL query
                - phase: Phase number
        """
        # Extract table information
        table_schema = table_data.get("header", [])
        table_types = table_data.get("types", [])
        table_rows = table_data.get("rows", [])
        table_id = raw.get("table_id", "table")
        
        # Extract SQL structure
        sql = raw.get("sql", {})
        
        # Convert SQL to human-readable format
        sql_readable = self.sql_to_readable(sql, table_schema)
        
        return {
            "question": raw.get("question", ""),
            "table_id": table_id,
            "table_schema": table_schema,
            "table_types": table_types,
            "table_rows": table_rows,
            "sql": sql,
            "sql_readable": sql_readable,
            "phase": raw.get("phase", 1)
        }
    
    def sql_to_readable(self, sql: Dict, headers: List[str]) -> str:
        """
        Convert SQL structure (sel, conds, agg) to human-readable SQL string.
        
        SQL Structure:
            sel: Column index for SELECT
            agg: Aggregation index (0=none, 1=MAX, 2=MIN, 3=COUNT, 4=SUM, 5=AVG)
            conds: List of [column_idx, operator_idx, value]
        
        Args:
            sql: Dictionary with sel, conds, agg keys
            headers: List of column names from table schema
        
        Returns:
            Human-readable SQL query string
        """
        if not sql:
            return ""
        
        sel = sql.get("sel", 0)
        agg = sql.get("agg", 0)
        conds = sql.get("conds", [])
        
        # Get selected column name
        if sel < len(headers):
            col_name = headers[sel]
        else:
            col_name = f"col{sel}"
        
        # Build SELECT clause with aggregation
        if 0 < agg < len(AGG_OPS):
            select_clause = f"{AGG_OPS[agg]}({col_name})"
        else:
            select_clause = col_name
        
        # Start building SQL
        sql_str = f"SELECT {select_clause} FROM table"
        
        # Build WHERE clause from conditions
        if conds:
            where_parts = []
            for cond in conds:
                if len(cond) >= 3:
                    col_idx, op_idx, value = cond[0], cond[1], cond[2]
                    
                    # Get column name
                    if col_idx < len(headers):
                        cond_col = headers[col_idx]
                    else:
                        cond_col = f"col{col_idx}"
                    
                    # Get operator
                    if op_idx < len(COND_OPS):
                        op = COND_OPS[op_idx]
                    else:
                        op = "="
                    
                    # Format value (quote strings)
                    if isinstance(value, str):
                        value = f"'{value}'"
                    
                    where_parts.append(f"{cond_col} {op} {value}")
            
            if where_parts:
                sql_str += " WHERE " + " AND ".join(where_parts)
        
        return sql_str
    
    # -------------------------------------------------------------------------
    # CONVENIENCE METHODS
    # -------------------------------------------------------------------------
    
    def get_example(self, index: int = 0, split: str = "train") -> Dict:
        """
        Get a single example by index.
        
        Args:
            index: Index of the example to retrieve
            split: Dataset split to load from
        
        Returns:
            Parsed example dictionary
        """
        examples = self.load_jsonl(split)
        
        if index < 0 or index >= len(examples):
            raise IndexError(f"Index {index} out of range. Dataset has {len(examples)} examples.")
        
        return examples[index]
    
    def get_schema_info(self, example: Dict) -> Dict:
        """
        Extract and serialize schema information from an example.
        
        Args:
            example: Parsed example dictionary
        
        Returns:
            Schema information dictionary (JSON serializable)
        """
        return {
            "table_id": example.get("table_id", "table"),
            "columns": example.get("table_schema", []),
            "types": example.get("table_types", []),
            "column_count": len(example.get("table_schema", [])),
            "row_count": len(example.get("table_rows", []))
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def load_wikisql_example(index: int = 0) -> Dict:
    """
    Load a single example from WikiSQL dataset.
    
    Args:
        index: Index of the example to load
    
    Returns:
        Dictionary containing:
            - question: Natural language question
            - table_schema: List of column names
            - table_name: Table identifier
            - human_readable_sql: SQL query string
            - sql_structure: Original SQL structure {sel, conds, agg}
    """
    loader = WikiSQLLoader()
    example = loader.get_example(index, split="train")
    
    return {
        "question": example["question"],
        "table_schema": example["table_schema"],
        "table_name": example["table_id"],
        "human_readable_sql": example["sql_readable"],
        "sql_structure": example["sql"],
        "table_types": example["table_types"],
    }


def get_schema_string(table_schema: List[str]) -> str:
    """
    Convert table schema (list of column names) to a formatted string.
    
    Args:
        table_schema: List of column header names
    
    Returns:
        Comma-separated string of column names
    """
    return ", ".join(table_schema)


# =============================================================================
# MAIN - Test the data loader
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  WikiSQL Data Loader Test")
    print("  Phase 1: Data Preparation")
    print("=" * 70)
    
    try:
        # Initialize loader
        loader = WikiSQLLoader()
        
        # Load first example
        example = loader.get_example(index=0, split="train")
        
        # Display results
        print(f"\n{'='*50}")
        print("EXAMPLE DATA")
        print('='*50)
        
        print(f"\n📝 Question:")
        print(f"   {example['question']}")
        
        print(f"\n📊 Table ID: {example['table_id']}")
        
        print(f"\n📋 Table Schema (columns):")
        for i, col in enumerate(example['table_schema']):
            col_type = example['table_types'][i] if i < len(example['table_types']) else 'unknown'
            print(f"   {i}: {col} ({col_type})")
        
        print(f"\n🔧 SQL Structure:")
        print(f"   sel (column):      {example['sql'].get('sel', 'N/A')}")
        print(f"   agg (aggregation): {AGG_OPS[example['sql'].get('agg', 0)] or 'None'}")
        print(f"   conds:             {example['sql'].get('conds', [])}")
        
        print(f"\n🎯 Generated SQL:")
        print(f"   {example['sql_readable']}")
        
        print(f"\n📄 Sample Rows ({len(example['table_rows'])} total):")
        for i, row in enumerate(example['table_rows'][:3]):
            print(f"   Row {i}: {row[:3]}..." if len(row) > 3 else f"   Row {i}: {row}")
        
        # Schema serialization
        print(f"\n📦 Schema (JSON serialized):")
        schema_info = loader.get_schema_info(example)
        print(f"   {json.dumps(schema_info, indent=2)}")
        
        print("\n" + "=" * 70)
        print("✅ Data loader test completed successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
