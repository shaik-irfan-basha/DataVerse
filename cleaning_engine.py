"""
cleaning_engine.py - Conversational Data Cleaning & Transformation Engine for DataVerse

Provides deterministic, reversible data cleaning transformations on pandas DataFrames:
- Missing-value analysis and handling (fill mean/median/mode/constant, drop rows/columns)
- Duplicate-row detection and removal (exact and subset duplicates)
- Column type conversion (numeric, integer, datetime, string, boolean with safe coercion)
- Filtering invalid or unwanted rows (conditional expressions, bounds, outlier removal)
- Basic text normalization (strip, case conversion, substring replacement, special chars)
- Before-and-after preview generation with affected row/column/cell diff metrics
- Natural language intent parsing for interactive conversational clarification
"""

import re
import math
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

logger = logging.getLogger("dataverse.cleaning")


class DataCleaningEngine:
    """
    Core data cleaning and transformation engine.
    Stateless operations that take a DataFrame and return (transformed_df, metrics_dict).
    """

    # =========================================================================
    # 1. Missing-Value Analysis & Handling
    # =========================================================================

    @staticmethod
    def analyze_missing(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes missing/null values across all columns of the DataFrame.
        Returns total rows, total nulls, and detailed per-column breakdown.
        """
        total_rows = len(df)
        col_analyses = []
        total_null_cells = 0
        rows_with_any_null = int(df.isnull().any(axis=1).sum()) if total_rows > 0 else 0

        for col in df.columns:
            null_count = int(df[col].isnull().sum())
            total_null_cells += null_count
            null_pct = round((null_count / total_rows * 100), 2) if total_rows > 0 else 0.0
            is_numeric = pd.api.types.is_numeric_dtype(df[col])

            # Generate smart recommendations based on column type and missing rate
            if null_count == 0:
                rec_strategy = "complete"
                rec_label = "No missing values"
            elif null_pct > 60.0:
                rec_strategy = "drop_columns"
                rec_label = "Drop column (high missing rate > 60%)"
            elif is_numeric:
                rec_strategy = "fill_median"
                rec_label = "Fill with median value"
            else:
                rec_strategy = "fill_mode"
                rec_label = "Fill with most frequent value (mode)"

            col_analyses.append({
                "column": col,
                "data_type": str(df[col].dtype),
                "is_numeric": is_numeric,
                "null_count": null_count,
                "null_percentage": null_pct,
                "recommended_strategy": rec_strategy,
                "recommendation_label": rec_label
            })

        return {
            "total_rows": total_rows,
            "total_columns": len(df.columns),
            "total_null_cells": total_null_cells,
            "rows_with_any_null": rows_with_any_null,
            "rows_with_any_null_pct": round((rows_with_any_null / total_rows * 100), 2) if total_rows > 0 else 0.0,
            "columns": col_analyses
        }

    @staticmethod
    def clean_missing(
        df: pd.DataFrame,
        strategy: str,
        columns: Optional[List[str]] = None,
        fill_value: Any = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Handles missing values using the requested strategy.
        Strategies: 'drop_rows', 'drop_columns', 'fill_mean', 'fill_median', 'fill_mode',
                    'fill_constant', 'fill_forward', 'fill_backward'.
        """
        cleaned = df.copy()
        target_cols = [c for c in columns if c in cleaned.columns] if columns else list(cleaned.columns)

        if not target_cols and strategy != 'drop_rows':
            raise ValueError("No valid target columns specified for missing value handling.")

        cells_modified = 0
        rows_before = len(cleaned)

        if strategy == "drop_rows":
            subset = target_cols if columns else None
            cleaned = cleaned.dropna(subset=subset).reset_index(drop=True)
            rows_affected = rows_before - len(cleaned)
            cells_modified = rows_affected * len(df.columns)
            summary = f"Dropped {rows_affected} row(s) containing missing values."

        elif strategy == "drop_columns":
            cols_to_drop = target_cols if columns else [c for c in cleaned.columns if cleaned[c].isnull().any()]
            if not cols_to_drop:
                return cleaned, {"rows_affected": 0, "cells_modified": 0, "summary": "No columns had missing values to drop."}
            cleaned = cleaned.drop(columns=cols_to_drop)
            cells_modified = sum(int(df[c].isnull().sum()) for c in cols_to_drop)
            summary = f"Dropped {len(cols_to_drop)} column(s): {', '.join(cols_to_drop)}."

        elif strategy == "fill_mean":
            for col in target_cols:
                if not pd.api.types.is_numeric_dtype(cleaned[col]):
                    # Attempt coercion to numeric
                    coerced = pd.to_numeric(cleaned[col], errors='coerce')
                    if coerced.isnull().all():
                        raise ValueError(f"Cannot calculate mean for non-numeric column '{col}'.")
                    cleaned[col] = coerced
                null_mask = cleaned[col].isnull()
                count = int(null_mask.sum())
                if count > 0:
                    mean_val = round(float(cleaned[col].mean()), 4)
                    cleaned[col] = cleaned[col].fillna(mean_val)
                    cells_modified += count
            summary = f"Filled missing values in {len(target_cols)} column(s) with mean value."

        elif strategy == "fill_median":
            for col in target_cols:
                if not pd.api.types.is_numeric_dtype(cleaned[col]):
                    coerced = pd.to_numeric(cleaned[col], errors='coerce')
                    if coerced.isnull().all():
                        raise ValueError(f"Cannot calculate median for non-numeric column '{col}'.")
                    cleaned[col] = coerced
                null_mask = cleaned[col].isnull()
                count = int(null_mask.sum())
                if count > 0:
                    med_val = round(float(cleaned[col].median()), 4)
                    cleaned[col] = cleaned[col].fillna(med_val)
                    cells_modified += count
            summary = f"Filled missing values in {len(target_cols)} column(s) with median value."

        elif strategy == "fill_mode":
            for col in target_cols:
                null_mask = cleaned[col].isnull()
                count = int(null_mask.sum())
                if count > 0:
                    modes = cleaned[col].mode(dropna=True)
                    if not modes.empty:
                        cleaned[col] = cleaned[col].fillna(modes.iloc[0])
                        cells_modified += count
            summary = f"Filled missing values in {len(target_cols)} column(s) with most frequent value (mode)."

        elif strategy == "fill_constant":
            val = fill_value if fill_value is not None else 0
            for col in target_cols:
                null_mask = cleaned[col].isnull()
                count = int(null_mask.sum())
                if count > 0:
                    cleaned[col] = cleaned[col].fillna(val)
                    cells_modified += count
            summary = f"Filled missing values in {len(target_cols)} column(s) with constant '{val}'."

        elif strategy == "fill_forward":
            for col in target_cols:
                null_count = int(cleaned[col].isnull().sum())
                cleaned[col] = cleaned[col].ffill()
                new_null = int(cleaned[col].isnull().sum())
                cells_modified += (null_count - new_null)
            summary = f"Forward-filled missing values in {len(target_cols)} column(s)."

        elif strategy == "fill_backward":
            for col in target_cols:
                null_count = int(cleaned[col].isnull().sum())
                cleaned[col] = cleaned[col].bfill()
                new_null = int(cleaned[col].isnull().sum())
                cells_modified += (null_count - new_null)
            summary = f"Backward-filled missing values in {len(target_cols)} column(s)."

        else:
            raise ValueError(f"Unknown missing value strategy: '{strategy}'")

        return cleaned, {
            "rows_affected": abs(rows_before - len(cleaned)),
            "cells_modified": cells_modified,
            "summary": summary
        }

    # =========================================================================
    # 2. Duplicate-Row Detection & Removal
    # =========================================================================

    @staticmethod
    def analyze_duplicates(df: pd.DataFrame, subset: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Analyzes duplicate rows across all columns or a specified subset.
        """
        total_rows = len(df)
        if total_rows == 0:
            return {
                "total_rows": 0,
                "duplicate_count": 0,
                "duplicate_percentage": 0.0,
                "subset_columns": subset or list(df.columns),
                "sample_duplicates": []
            }

        valid_subset = [c for c in subset if c in df.columns] if subset else None
        dup_mask = df.duplicated(subset=valid_subset, keep=False)
        dup_count = int(df.duplicated(subset=valid_subset, keep='first').sum())
        dup_pct = round((dup_count / total_rows * 100), 2)

        # Get duplicate sample rows (up to 5)
        sample_df = df[dup_mask].head(6)
        sample_rows = DataCleaningEngine._df_to_records(sample_df)

        return {
            "total_rows": total_rows,
            "duplicate_count": dup_count,
            "duplicate_percentage": dup_pct,
            "subset_columns": valid_subset or list(df.columns),
            "sample_duplicates": sample_rows
        }

    @staticmethod
    def clean_duplicates(
        df: pd.DataFrame,
        subset: Optional[List[str]] = None,
        keep: str = "first"
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Removes duplicate rows based on all columns or a subset of columns.
        keep: 'first', 'last', or False (drop all duplicates).
        """
        valid_subset = [c for c in subset if c in df.columns] if subset else None
        rows_before = len(df)
        cleaned = df.drop_duplicates(subset=valid_subset, keep=keep).reset_index(drop=True)
        rows_dropped = rows_before - len(cleaned)

        subset_desc = f" on columns ({', '.join(valid_subset)})" if valid_subset else " across all columns"
        return cleaned, {
            "rows_affected": rows_dropped,
            "cells_modified": rows_dropped * len(df.columns),
            "summary": f"Removed {rows_dropped} duplicate row(s){subset_desc} (retained {keep} occurrence)."
        }

    # =========================================================================
    # 3. Column Type Conversion
    # =========================================================================

    @staticmethod
    def clean_convert_type(
        df: pd.DataFrame,
        column: str,
        target_type: str,
        errors: str = "coerce"
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Converts column data type safely with validation and failure tracking.
        target_type: 'numeric', 'integer', 'datetime', 'string', 'boolean'.
        """
        if column not in df.columns:
            raise ValueError(f"Column '{column}' does not exist in dataset. Available: {list(df.columns)}")

        cleaned = df.copy()
        orig_dtype = str(cleaned[column].dtype)
        target_type = target_type.lower().strip()
        failed_count = 0
        nulls_before = int(cleaned[column].isnull().sum())

        if target_type in ("numeric", "float", "number"):
            converted = pd.to_numeric(cleaned[column], errors=errors)
            failed_count = int(converted.isnull().sum()) - nulls_before
            cleaned[column] = converted
            new_dtype = "float64"

        elif target_type in ("integer", "int"):
            converted = pd.to_numeric(cleaned[column], errors=errors)
            failed_count = int(converted.isnull().sum()) - nulls_before
            # Use pandas nullable integer to preserve NaNs without crashing
            cleaned[column] = converted.round().astype("Int64")
            new_dtype = "Int64"

        elif target_type in ("datetime", "date", "timestamp"):
            converted = pd.to_datetime(cleaned[column], errors=errors)
            failed_count = int(converted.isnull().sum()) - nulls_before
            cleaned[column] = converted
            new_dtype = "datetime64[ns]"

        elif target_type in ("string", "text", "str"):
            cleaned[column] = cleaned[column].fillna("").astype(str)
            new_dtype = "string"

        elif target_type in ("boolean", "bool"):
            true_values = {"true", "1", "1.0", "t", "yes", "y", "sim", "vrai"}
            false_values = {"false", "0", "0.0", "f", "no", "n", "nao", "faux"}

            def parse_bool(v):
                if pd.isnull(v) or v == "":
                    return None
                s = str(v).strip().lower()
                if s in true_values:
                    return True
                if s in false_values:
                    return False
                return None

            converted = cleaned[column].apply(parse_bool)
            failed_count = int(converted.isnull().sum()) - nulls_before
            cleaned[column] = converted.astype("boolean")
            new_dtype = "boolean"

        else:
            raise ValueError(f"Unsupported target type: '{target_type}'. Supported: numeric, integer, datetime, string, boolean.")

        cells_modified = len(cleaned) - nulls_before
        warning = f"{failed_count} values could not be parsed and were converted to NULL." if failed_count > 0 else ""

        return cleaned, {
            "rows_affected": 0,
            "cells_modified": cells_modified,
            "failed_conversions": max(failed_count, 0),
            "original_dtype": orig_dtype,
            "new_dtype": new_dtype,
            "warning": warning,
            "summary": f"Converted column '{column}' from {orig_dtype} to {new_dtype}." + (f" ({warning})" if warning else "")
        }

    # =========================================================================
    # 4. Filtering Invalid or Unwanted Rows
    # =========================================================================

    @staticmethod
    def clean_filter_rows(
        df: pd.DataFrame,
        column: str,
        operator: str,
        value: Any = None,
        min_val: Any = None,
        max_val: Any = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Filters out invalid, unwanted, or outlier rows based on a condition.
        Operators: 'greater_than', 'less_than', 'greater_or_equal', 'less_or_equal',
                   'equals', 'not_equals', 'between', 'not_null', 'drop_outliers', 'remove_negative'.
        """
        if column not in df.columns:
            raise ValueError(f"Column '{column}' does not exist in dataset. Available: {list(df.columns)}")

        cleaned = df.copy()
        rows_before = len(cleaned)
        op = operator.lower().strip()

        if op in ("greater_than", ">"):
            val = float(value)
            cleaned = cleaned[cleaned[column] > val].reset_index(drop=True)
            summary = f"Filtered to rows where '{column}' > {val}."

        elif op in ("greater_or_equal", ">="):
            val = float(value)
            cleaned = cleaned[cleaned[column] >= val].reset_index(drop=True)
            summary = f"Filtered to rows where '{column}' >= {val}."

        elif op in ("less_than", "<"):
            val = float(value)
            cleaned = cleaned[cleaned[column] < val].reset_index(drop=True)
            summary = f"Filtered to rows where '{column}' < {val}."

        elif op in ("less_or_equal", "<="):
            val = float(value)
            cleaned = cleaned[cleaned[column] <= val].reset_index(drop=True)
            summary = f"Filtered to rows where '{column}' <= {val}."

        elif op in ("equals", "==", "eq"):
            cleaned = cleaned[cleaned[column] == value].reset_index(drop=True)
            summary = f"Filtered to rows where '{column}' == '{value}'."

        elif op in ("not_equals", "!=", "neq"):
            cleaned = cleaned[cleaned[column] != value].reset_index(drop=True)
            summary = f"Filtered out rows where '{column}' == '{value}'."

        elif op == "between":
            low = float(min_val) if min_val is not None else float('-inf')
            high = float(max_val) if max_val is not None else float('inf')
            cleaned = cleaned[(cleaned[column] >= low) & (cleaned[column] <= high)].reset_index(drop=True)
            summary = f"Filtered rows where '{column}' is between {low} and {high}."

        elif op in ("not_null", "drop_null", "non_empty"):
            cleaned = cleaned[cleaned[column].notnull() & (cleaned[column].astype(str).str.strip() != "")].reset_index(drop=True)
            summary = f"Filtered out empty or null rows in column '{column}'."

        elif op in ("remove_negative", "non_negative"):
            numeric_col = pd.to_numeric(cleaned[column], errors='coerce')
            cleaned = cleaned[numeric_col >= 0].reset_index(drop=True)
            summary = f"Filtered out negative values in '{column}'."

        elif op in ("drop_outliers", "remove_outliers"):
            numeric_col = pd.to_numeric(cleaned[column], errors='coerce')
            q1 = numeric_col.quantile(0.25)
            q3 = numeric_col.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            cleaned = cleaned[(numeric_col >= lower_bound) & (numeric_col <= upper_bound)].reset_index(drop=True)
            summary = f"Removed IQR outliers in '{column}' (bounds: {round(lower_bound, 2)} to {round(upper_bound, 2)})."

        else:
            raise ValueError(f"Unsupported filter operator: '{operator}'")

        rows_dropped = rows_before - len(cleaned)
        warning = "Warning: This filter dropped 100% of rows in the dataset." if len(cleaned) == 0 else ""

        return cleaned, {
            "rows_affected": rows_dropped,
            "cells_modified": rows_dropped * len(df.columns),
            "rows_retained": len(cleaned),
            "warning": warning,
            "summary": summary
        }

    # =========================================================================
    # 5. Basic Text Normalization
    # =========================================================================

    @staticmethod
    def clean_normalize_text(
        df: pd.DataFrame,
        columns: List[str],
        operations: List[str],
        replace_old: Optional[str] = None,
        replace_new: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Normalizes text columns: strip, lower, upper, title, replace, remove_special.
        """
        target_cols = [c for c in columns if c in df.columns]
        if not target_cols:
            raise ValueError(f"No valid target columns found in dataset. Requested: {columns}, Available: {list(df.columns)}")

        cleaned = df.copy()
        cells_modified = 0
        applied_ops = []

        for col in target_cols:
            not_null_mask = cleaned[col].notnull() & (cleaned[col] != "None")
            series = cleaned[col].copy()
            if not not_null_mask.any():
                continue
            str_series = series[not_null_mask].astype(str)
            initial_series = str_series.copy()

            for op in operations:
                op_clean = op.lower().strip()
                if op_clean in ("strip", "trim"):
                    str_series = str_series.str.strip()
                    if "strip" not in applied_ops: applied_ops.append("strip whitespace")
                elif op_clean in ("lower", "lowercase"):
                    str_series = str_series.str.lower()
                    if "lowercase" not in applied_ops: applied_ops.append("lowercase")
                elif op_clean in ("upper", "uppercase"):
                    str_series = str_series.str.upper()
                    if "uppercase" not in applied_ops: applied_ops.append("uppercase")
                elif op_clean in ("title", "titlecase", "capitalize"):
                    str_series = str_series.str.title()
                    if "title case" not in applied_ops: applied_ops.append("title case")
                elif op_clean == "remove_special":
                    str_series = str_series.str.replace(r'[^a-zA-Z0-9\s]', '', regex=True).str.strip()
                    if "remove special characters" not in applied_ops: applied_ops.append("remove special characters")
                elif op_clean == "collapse_whitespace":
                    str_series = str_series.str.replace(r'\s+', ' ', regex=True).str.strip()
                    if "collapse whitespace" not in applied_ops: applied_ops.append("collapse whitespace")
                elif op_clean == "replace" and replace_old is not None:
                    repl_to = replace_new if replace_new is not None else ""
                    str_series = str_series.str.replace(str(replace_old), str(repl_to), regex=False)
                    if f"replace '{replace_old}'" not in applied_ops: applied_ops.append(f"replace '{replace_old}' with '{repl_to}'")

            changed_mask = (initial_series != str_series)
            cells_modified += int(changed_mask.sum())
            series[not_null_mask] = str_series
            cleaned[col] = series

        summary = f"Normalized {len(target_cols)} column(s) ({', '.join(target_cols)}) with: {', '.join(applied_ops)}."
        return cleaned, {
            "rows_affected": 0,
            "cells_modified": cells_modified,
            "operations_applied": applied_ops,
            "columns_affected": target_cols,
            "summary": summary
        }

    # =========================================================================
    # 6. Unified Preview Generation
    # =========================================================================

    @classmethod
    def generate_preview(cls, df: pd.DataFrame, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a proposed cleaning plan against a copy of df and generates
        a comprehensive preview: before vs after rows/columns, affected counts,
        and side-by-side sample records.
        """
        operation = plan.get("operation")
        params = plan.get("params", {})
        table_name = plan.get("table_name", "dataset")

        if df is None:
            raise ValueError("No active dataset loaded to clean.")

        rows_before = len(df)
        cols_before = list(df.columns)

        # Validate column existence if specific column requested
        req_col = params.get("column")
        if req_col and req_col not in cols_before:
            raise ValueError(f"Column '{req_col}' does not exist in dataset. Available: {cols_before}")

        if len(cols_before) == 0:
            return {
                "operation": operation or "unknown",
                "table_name": table_name,
                "description": "Dataset has no columns. No changes needed.",
                "rows_before": 0,
                "rows_after": 0,
                "rows_affected": 0,
                "columns_before": [],
                "columns_after": [],
                "columns_affected": [],
                "cells_modified": 0,
                "is_destructive": False,
                "warning": "Dataset has no columns.",
                "before_sample": [],
                "after_sample": [],
                "transformed_df": df.copy()
            }


        # Dispatch transformation
        warning = ""
        if operation == "handle_missing":
            transformed_df, metrics = cls.clean_missing(
                df=df,
                strategy=params.get("strategy", "drop_rows"),
                columns=params.get("columns"),
                fill_value=params.get("fill_value")
            )
            columns_affected = params.get("columns") or cols_before
            is_destructive = params.get("strategy") in ("drop_rows", "drop_columns")

        elif operation == "remove_duplicates":
            transformed_df, metrics = cls.clean_duplicates(
                df=df,
                subset=params.get("subset"),
                keep=params.get("keep", "first")
            )
            columns_affected = params.get("subset") or cols_before
            is_destructive = metrics.get("rows_affected", 0) > 0

        elif operation == "convert_type":
            transformed_df, metrics = cls.clean_convert_type(
                df=df,
                column=params.get("column", cols_before[0]),
                target_type=params.get("target_type", "string"),
                errors=params.get("errors", "coerce")
            )
            columns_affected = [params.get("column", cols_before[0])]
            is_destructive = metrics.get("failed_conversions", 0) > 0
            warning = metrics.get("warning", "")

        elif operation == "filter_rows":
            transformed_df, metrics = cls.clean_filter_rows(
                df=df,
                column=params.get("column", cols_before[0]),
                operator=params.get("operator", "not_null"),
                value=params.get("value"),
                min_val=params.get("min_val"),
                max_val=params.get("max_val")
            )
            columns_affected = [params.get("column", cols_before[0])]
            is_destructive = metrics.get("rows_affected", 0) > 0
            warning = metrics.get("warning", "")

        elif operation == "normalize_text":
            transformed_df, metrics = cls.clean_normalize_text(
                df=df,
                columns=params.get("columns", cols_before),
                operations=params.get("operations", ["strip"]),
                replace_old=params.get("replace_old"),
                replace_new=params.get("replace_new")
            )
            columns_affected = metrics.get("columns_affected", [])
            is_destructive = False

        else:
            raise ValueError(f"Unknown cleaning operation: '{operation}'")

        rows_after = len(transformed_df)
        cols_after = list(transformed_df.columns)
        rows_affected = metrics.get("rows_affected", abs(rows_before - rows_after))
        cells_modified = metrics.get("cells_modified", 0)
        description = metrics.get("summary", plan.get("description", "Dataset transformation"))

        # Build clean JSON-serializable before and after samples (top 5 rows)
        before_sample = cls._df_to_records(df.head(5))
        after_sample = cls._df_to_records(transformed_df.head(5))

        return {
            "operation": operation,
            "table_name": table_name,
            "description": description,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_affected": rows_affected,
            "columns_before": cols_before,
            "columns_after": cols_after,
            "columns_affected": columns_affected,
            "cells_modified": cells_modified,
            "is_destructive": is_destructive,
            "warning": warning,
            "before_sample": before_sample,
            "after_sample": after_sample,
            "transformed_df": transformed_df
        }

    # =========================================================================
    # 7. Conversational Intent Parser
    # =========================================================================

    @classmethod
    def parse_cleaning_prompt(
        cls,
        prompt: str,
        columns: List[str],
        table_name: str = "dataset"
    ) -> Optional[Dict[str, Any]]:
        """
        Detects if a user question or input is a data cleaning intent.
        Returns a structured cleaning plan if matched, or None if it is a general SQL query.
        """
        text = prompt.strip()
        lower = text.lower()

        # Helper to find column referenced in text
        def find_referenced_column(cols: List[str]) -> Optional[str]:
            for c in cols:
                # Whole word match for column name (case insensitive)
                pattern = r'\b' + re.escape(c.lower()) + r'\b'
                if re.search(pattern, lower):
                    return c
            return None

        # 1. Missing Values: Fill (Median, Mean, Mode, Constant, Forward, Backward)
        fill_match = re.search(r'\bfill\s+(missing|null|na|nan)(\s+values?)?(\s+in\s+([a-zA-Z0-9_]+))?\s+with\s+(.+)', lower)
        if fill_match:
            col_target = fill_match.group(4) or find_referenced_column(columns)
            fill_target_str = fill_match.group(5).strip()

            if "median" in fill_target_str:
                strategy = "fill_median"
                fill_val = None
            elif "mean" in fill_target_str or "average" in fill_target_str:
                strategy = "fill_mean"
                fill_val = None
            elif "mode" in fill_target_str or "most frequent" in fill_target_str:
                strategy = "fill_mode"
                fill_val = None
            elif "forward" in fill_target_str or "ffill" in fill_target_str:
                strategy = "fill_forward"
                fill_val = None
            elif "backward" in fill_target_str or "bfill" in fill_target_str:
                strategy = "fill_backward"
                fill_val = None
            else:
                strategy = "fill_constant"
                raw_val = fill_target_str.strip("'\"`")
                try:
                    fill_val = float(raw_val) if "." in raw_val else int(raw_val)
                except ValueError:
                    fill_val = raw_val

            return {
                "operation": "handle_missing",
                "table_name": table_name,
                "description": f"Fill missing values in {col_target or 'columns'} with {fill_target_str}.",
                "params": {
                    "strategy": strategy,
                    "columns": [col_target] if col_target else None,
                    "fill_value": fill_val
                }
            }

        # 2. Missing Values: Drop Rows
        if re.search(r'\b(drop|remove|delete)\s+(rows?\s+with\s+)?(missing|null|na|nan)(\s+rows?|\s+values?)?\b', lower) or \
           re.search(r'\bdrop\s*na\b', lower):
            ref_col = find_referenced_column(columns)
            return {
                "operation": "handle_missing",
                "table_name": table_name,
                "description": f"Drop rows with missing values" + (f" in column '{ref_col}'" if ref_col else " across all columns"),
                "params": {"strategy": "drop_rows", "columns": [ref_col] if ref_col else None}
            }

        # 3. Missing Values: Drop Columns
        if re.search(r'\b(drop|remove|delete)\s+(columns?\s+with\s+)?(missing|null|na|nan)(\s+columns?)?\b', lower):
            ref_col = find_referenced_column(columns)
            return {
                "operation": "handle_missing",
                "table_name": table_name,
                "description": f"Drop column '{ref_col}' due to missing values" if ref_col else "Drop columns containing missing values",
                "params": {"strategy": "drop_columns", "columns": [ref_col] if ref_col else None}
            }

        # 4. Missing Values: Check / Analysis
        if re.search(r'\b(check|find|analyze|show|inspect|count)\s+(for\s+)?(missing|null|na|nan)\b', lower) or \
           re.search(r'\bmissing\s+values?\s+(analysis|summary|check|report)\b', lower) or \
           re.match(r'^\s*(check\s+)?(missing|null)\s*(values?)?\s*$', lower):
            ref_col = find_referenced_column(columns)
            return {
                "operation": "analyze_missing",
                "table_name": table_name,
                "description": "Analyze missing values across dataset columns.",
                "params": {"columns": [ref_col] if ref_col else None}
            }

        # 5. Duplicates: Remove
        if re.search(r'\b(remove|drop|delete|clean)\s+(all\s+)?duplicates?(\s+rows?)?\b', lower) or \
           re.search(r'\b(remove|drop|delete)\s+(duplicate\s+rows?)\b', lower) or \
           re.search(r'\bdeduplicate(\s+dataset|\s+table|\s+rows?)?\b', lower) or \
           re.search(r'\bdedup\b', lower):
            ref_col = find_referenced_column(columns)
            return {
                "operation": "remove_duplicates",
                "table_name": table_name,
                "description": f"Remove duplicate rows" + (f" based on column '{ref_col}'" if ref_col else " across all columns"),
                "params": {"subset": [ref_col] if ref_col else None, "keep": "first"}
            }

        # 6. Duplicates: Analysis / Check
        if re.search(r'\b(check|find|analyze|show|inspect|count)\s+(for\s+)?(all\s+)?duplicates?(\s+rows?)?\b', lower) or \
           re.search(r'\bduplicate\s+(rows?\s+)?(analysis|check|summary|report)\b', lower) or \
           re.match(r'^\s*(check\s+)?duplicates?\s*(rows?)?\s*$', lower):
            ref_col = find_referenced_column(columns)
            return {
                "operation": "analyze_duplicates",
                "table_name": table_name,
                "description": "Analyze duplicate rows in dataset.",
                "params": {"subset": [ref_col] if ref_col else None}
            }

        # 7. Type Conversion: convert <col> to <type>
        conv_match = re.search(r'\bconvert\s+([a-zA-Z0-9_]+)\s+to\s+([a-zA-Z0-9_]+)\b', lower) or \
                     re.search(r'\bcast\s+([a-zA-Z0-9_]+)\s+(as|to)\s+([a-zA-Z0-9_]+)\b', lower) or \
                     re.search(r'\bchange\s+([a-zA-Z0-9_]+)\s+type\s+to\s+([a-zA-Z0-9_]+)\b', lower)
        if conv_match:
            col_cand = conv_match.group(1)
            type_cand = conv_match.group(2) if conv_match.lastindex == 2 else conv_match.group(3)
            # Find closest matching real column
            real_col = next((c for c in columns if c.lower() == col_cand.lower()), None)
            if real_col:
                return {
                    "operation": "convert_type",
                    "table_name": table_name,
                    "description": f"Convert column '{real_col}' to {type_cand}.",
                    "params": {"column": real_col, "target_type": type_cand}
                }

        # 8. Text Normalization: trim, lowercase, uppercase, title case
        ref_col = find_referenced_column(columns)
        if ref_col:
            ops = []
            if re.search(r'\b(trim|strip)\b', lower):
                ops.append("strip")
            if re.search(r'\b(lower|lowercase)\b', lower):
                ops.append("lower")
            if re.search(r'\b(upper|uppercase)\b', lower):
                ops.append("upper")
            if re.search(r'\b(title\s*case|capitalize)\b', lower):
                ops.append("title")
            if re.search(r'\bremove\s+special\s+char(acter)?s?\b', lower):
                ops.append("remove_special")
            if ops:
                return {
                    "operation": "normalize_text",
                    "table_name": table_name,
                    "description": f"Normalize column '{ref_col}' with: {', '.join(ops)}.",
                    "params": {"columns": [ref_col], "operations": ops}
                }

        # 9. Row Filtering / Outlier removal
        if re.search(r'\b(drop|remove|filter\s+out)\s+outliers\b', lower):
            ref_col = find_referenced_column(columns)
            if ref_col:
                return {
                    "operation": "filter_rows",
                    "table_name": table_name,
                    "description": f"Remove statistical outliers in '{ref_col}' using IQR bounds.",
                    "params": {"column": ref_col, "operator": "drop_outliers"}
                }

        if re.search(r'\b(drop|remove|filter\s+out)\s+negative(\s+values?)?\b', lower):
            ref_col = find_referenced_column(columns)
            if ref_col:
                return {
                    "operation": "filter_rows",
                    "table_name": table_name,
                    "description": f"Filter out negative values in '{ref_col}'.",
                    "params": {"column": ref_col, "operator": "remove_negative"}
                }

        # Keep / filter to rows where condition
        filter_keep_match = re.search(r'\b(filter|keep)\s+(to\s+)?(rows?\s+)?where\s+([a-zA-Z0-9_]+)\s*(<|<=|>|>=|!=|==|=)\s*([0-9.-]+)\b', lower)
        if filter_keep_match:
            col_name = filter_keep_match.group(4)
            op_sym = filter_keep_match.group(5)
            val_num = float(filter_keep_match.group(6))
            real_col = next((c for c in columns if c.lower() == col_name.lower()), None)
            if real_col:
                op_map = {"=": "==", "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
                keep_op = op_map.get(op_sym, "==")
                return {
                    "operation": "filter_rows",
                    "table_name": table_name,
                    "description": f"Filter rows where '{real_col}' {op_sym} {val_num}.",
                    "params": {"column": real_col, "operator": keep_op, "value": val_num}
                }

        # Drop rows where condition (inverts operator)
        filter_cond_match = re.search(r'\b(drop|remove|delete)\s+rows?\s+where\s+([a-zA-Z0-9_]+)\s*(<|<=|>|>=|!=|==|=)\s*([0-9.-]+)\b', lower)
        if filter_cond_match:
            col_name = filter_cond_match.group(2)
            op_sym = filter_cond_match.group(3)
            val_num = float(filter_cond_match.group(4))
            real_col = next((c for c in columns if c.lower() == col_name.lower()), None)
            if real_col:
                inv_map = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}
                keep_op = inv_map.get(op_sym, "!=")
                return {
                    "operation": "filter_rows",
                    "table_name": table_name,
                    "description": f"Drop rows where '{real_col}' {op_sym} {val_num}.",
                    "params": {"column": real_col, "operator": keep_op, "value": val_num}
                }


        return None

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Converts DataFrame to JSON-safe dictionary records with NaN and Timestamp handling."""
        records = []
        for row in df.to_dict(orient="records"):
            clean_row = {}
            for k, v in row.items():
                if v is None or pd.isna(v):
                    clean_row[k] = None
                elif isinstance(v, (np.integer, int)):
                    clean_row[k] = int(v)
                elif isinstance(v, (np.floating, float)):
                    clean_row[k] = round(float(v), 4)
                elif isinstance(v, (pd.Timestamp, np.datetime64)):
                    clean_row[k] = v.isoformat() if hasattr(v, 'isoformat') else str(v)
                else:
                    clean_row[k] = str(v)
            records.append(clean_row)
        return records


cleaning_engine = DataCleaningEngine()
