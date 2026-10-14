"""
data_profiler.py - Automated Data Profiler for DataVerse

Analyzes loaded tables to extract comprehensive statistical summaries:
- Column data types and completeness (null rates)
- Cardinality and uniqueness metrics
- Numeric distributions (min, max, mean, median, std)
- Categorical distributions (top values and frequencies)
- Formats profiles as structured dataclasses, dictionaries, and Markdown summaries.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import sqlite3
import logging
import math
import pandas as pd
from data_connector import DataConnector

logger = logging.getLogger("dataverse.profiler")

@dataclass
class ColumnProfile:
    name: str
    data_type: str
    total_count: int
    null_count: int
    null_percentage: float
    unique_count: int
    unique_percentage: float
    # Numeric metrics
    is_numeric: bool = False
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    median_val: Optional[float] = None
    std_val: Optional[float] = None
    # Categorical metrics
    top_values: List[Dict[str, Any]] = field(default_factory=list) # [{"value": "...", "count": 10, "pct": 25.0}]
    sample_values: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableProfile:
    table_name: str
    total_rows: int
    total_columns: int
    columns: List[ColumnProfile] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "columns": [col.to_dict() for col in self.columns]
        }


class DataProfiler:
    """
    Computes statistical profiles for tables in DataConnector.
    """
    
    @staticmethod
    def profile_table(connector: DataConnector, table_name: str, max_sample_rows: int = 50000) -> TableProfile:
        """
        Profiles a specific table from the connector.
        Safely samples if the table exceeds max_sample_rows for performance.
        """
        with connector._lock:
            conn = connector.get_connection()
            safe_table = connector._quote_identifier(table_name)
            
            # Check row count
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {safe_table}")
            total_rows = cursor.fetchone()[0]
            
            if total_rows == 0:
                # Read column schema
                cursor.execute(f"PRAGMA table_info({safe_table})")
                col_infos = cursor.fetchall()
                cols = [
                    ColumnProfile(
                        name=c[1],
                        data_type=c[2] or "TEXT",
                        total_count=0,
                        null_count=0,
                        null_percentage=0.0,
                        unique_count=0,
                        unique_percentage=0.0
                    ) for c in col_infos
                ]
                return TableProfile(table_name=table_name, total_rows=0, total_columns=len(cols), columns=cols)
            
            # Read data into DataFrame
            query = f"SELECT * FROM {safe_table}"
            if total_rows > max_sample_rows:
                query += f" LIMIT {max_sample_rows}"
            df = pd.read_sql_query(query, conn)
            
            column_profiles = []
            for col_name in df.columns:
                series = df[col_name]
                col_len = len(series)
                null_count = int(series.isna().sum())
                null_pct = round((null_count / col_len) * 100, 2) if col_len > 0 else 0.0
                non_null_series = series.dropna()
                non_null_count = len(non_null_series)
                unique_count = int(non_null_series.nunique())
                unique_pct = round((unique_count / non_null_count) * 100, 2) if non_null_count > 0 else 0.0
                
                # Sample values
                sample_vals = [x for x in non_null_series.head(5).tolist()]
                
                is_numeric = False
                min_v = max_v = mean_v = median_v = std_v = None
                top_vals = []
                
                # Check numeric
                if pd.api.types.is_numeric_dtype(series):
                    is_numeric = True
                    if non_null_count > 0:
                        min_v = float(non_null_series.min())
                        max_v = float(non_null_series.max())
                        mean_v = round(float(non_null_series.mean()), 3)
                        median_v = round(float(non_null_series.median()), 3)
                        std_calc = non_null_series.std()
                        std_v = round(float(std_calc), 3) if not math.isnan(std_calc) else 0.0
                else:
                    # Categorical top values
                    if non_null_count > 0:
                        vc = non_null_series.value_counts().head(5)
                        for val, count in vc.items():
                            val_str = str(val)[:50]
                            top_vals.append({
                                "value": val_str,
                                "count": int(count),
                                "percentage": round((count / non_null_count) * 100, 1)
                            })
                
                # Determine data type string
                dtype_str = str(series.dtype)
                if is_numeric:
                    dtype_str = "FLOAT" if "float" in dtype_str else "INTEGER"
                elif pd.api.types.is_datetime64_any_dtype(series):
                    dtype_str = "DATETIME"
                else:
                    dtype_str = "TEXT"
                
                col_profile = ColumnProfile(
                    name=str(col_name),
                    data_type=dtype_str,
                    total_count=total_rows,
                    null_count=null_count,
                    null_percentage=null_pct,
                    unique_count=unique_count,
                    unique_percentage=unique_pct,
                    is_numeric=is_numeric,
                    min_val=min_v,
                    max_val=max_v,
                    mean_val=mean_v,
                    median_val=median_v,
                    std_val=std_v,
                    top_values=top_vals,
                    sample_values=sample_vals
                )
                column_profiles.append(col_profile)
                
            return TableProfile(
                table_name=table_name,
                total_rows=total_rows,
                total_columns=len(column_profiles),
                columns=column_profiles
            )

    @staticmethod
    def profile_all_tables(connector: DataConnector) -> Dict[str, TableProfile]:
        """
        Profiles every loaded table in the connector.
        """
        profiles = {}
        with connector._lock:
            conn = connector.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [r[0] for r in cursor.fetchall()]
        
        for table in tables:
            profiles[table] = DataProfiler.profile_table(connector, table)
        return profiles

    @staticmethod
    def format_profile_markdown(profile: TableProfile) -> str:
        """
        Formats a TableProfile into clean Markdown suitable for display or logging.
        """
        lines = [
            f"### 📋 Table Profile: `{profile.table_name}`",
            f"**Total Records:** {profile.total_rows:,} | **Total Columns:** {profile.total_columns}",
            "",
            "| Column | Type | Null % | Uniques | Summary Stats / Top Values |",
            "|:---|:---:|:---:|:---:|:---|"
        ]
        
        for col in profile.columns:
            null_info = f"{col.null_percentage}% ({col.null_count})"
            uniq_info = f"{col.unique_count} ({col.unique_percentage}%)"
            
            if col.is_numeric:
                stats = f"Range: [{col.min_val} to {col.max_val}] | Mean: {col.mean_val} | Med: {col.median_val}"
            elif col.top_values:
                top_str = ", ".join([f"'{v['value']}': {v['percentage']}%" for v in col.top_values[:3]])
                stats = f"Top: {top_str}"
            else:
                stats = "None"
                
            lines.append(f"| **{col.name}** | `{col.data_type}` | {null_info} | {uniq_info} | {stats} |")
            
        return "\n".join(lines)
