"""
schema_engine.py - Relational Schema Discovery, Relationship Inference & ER Visualizer Engine

Provides:
- Schema Discovery: Tables, columns, types, primary keys, explicit foreign keys, null rates, uniqueness.
- Relationship Inference: Heuristic inference based on naming patterns, compatible types,
  uniqueness, and value overlap percentages.
- Cardinality Determination: One-to-one (1:1), One-to-many (1:N), Many-to-many (N:M).
- Strict Distinction: Explicit / Confirmed vs. Inferred Candidates vs. Rejected.
- Relationship Persistence: Confirmed, rejected, and custom relationships per session/dataset.
- SQL Join Generator: Safe, validated dialect-accurate SQLite JOIN queries.
- Strict Session Isolation: No data or secrets bleed across sessions.
"""

import sqlite3
import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime

from data_connector import DataConnector
from sql_validator import SQLValidator
from metadata_manager import metadata_manager

logger = logging.getLogger("dataverse.schema_engine")

# Common generic column names that should NOT be matched across tables on exact name alone
GENERIC_COLUMN_NAMES = {
    "name", "title", "description", "status", "type", "category",
    "created_at", "updated_at", "deleted_at", "timestamp", "date",
    "value", "notes", "comment", "comments", "data", "count",
    "total", "amount", "price", "rate", "year", "month", "day"
}

NUMERIC_TYPES = {"int", "integer", "tinyint", "smallint", "mediumint", "bigint", "unsigned big int", "int2", "int8", "real", "double", "float", "numeric", "decimal"}
TEXT_TYPES = {"text", "character", "varchar", "varying character", "nchar", "native character", "nvarchar", "clob", "string"}
DATETIME_TYPES = {"date", "datetime", "timestamp", "time"}


def singularize(word: str) -> str:
    """Converts common English plural table names to singular form."""
    w = word.lower().strip()
    if w.endswith(("us", "is", "ss")):
        return w
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith(("sses", "shes", "ches", "xes", "zes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and len(w) > 2:
        return w[:-1]
    return w


def is_type_compatible(type_a: str, type_b: str) -> bool:
    """Checks if two SQLite column types are semantically compatible for joins."""
    ta = (type_a or "TEXT").lower().strip()
    tb = (type_b or "TEXT").lower().strip()

    # Exact or empty match (SQLite typeless affinity)
    if ta == tb or not ta or not tb:
        return True

    is_num_a = any(t in ta for t in NUMERIC_TYPES)
    is_num_b = any(t in tb for t in NUMERIC_TYPES)
    if is_num_a and is_num_b:
        return True

    is_txt_a = any(t in ta for t in TEXT_TYPES)
    is_txt_b = any(t in tb for t in TEXT_TYPES)
    if is_txt_a and is_txt_b:
        return True

    is_dt_a = any(t in ta for t in DATETIME_TYPES)
    is_dt_b = any(t in tb for t in DATETIME_TYPES)
    if is_dt_a and is_dt_b:
        return True

    return False


@dataclass
class ColumnDetail:
    name: str
    data_type: str
    is_pk: bool = False
    is_fk: bool = False
    fk_target_table: Optional[str] = None
    fk_target_column: Optional[str] = None
    is_nullable: bool = True
    total_count: int = 0
    null_count: int = 0
    null_rate: float = 0.0
    unique_count: int = 0
    unique_rate: float = 0.0
    sample_values: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableDetail:
    table_name: str
    row_count: int
    columns: List[ColumnDetail] = field(default_factory=list)
    primary_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "row_count": self.row_count,
            "columns": [c.to_dict() for c in self.columns],
            "primary_keys": self.primary_keys
        }


@dataclass
class RelationshipDetail:
    id: str  # "source_table.source_column->target_table.target_column"
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    cardinality: str  # 'one-to-one', 'one-to-many', 'many-to-many'
    status: str  # 'confirmed', 'inferred', 'rejected'
    confidence: float
    source: str  # 'explicit_fk', 'inferred', 'user_custom'
    overlap_percentage: float = 0.0
    overlap_count: int = 0
    sample_matches: List[Any] = field(default_factory=list)
    is_ambiguous: bool = False
    ambiguity_note: Optional[str] = None
    user_confirmed: bool = False
    user_rejected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RelationalSchemaEngine:
    """
    Engine for automated schema discovery, primary/foreign key detection,
    heuristic relationship inference, and safe SQL join generation.
    """

    def __init__(self):
        self.sql_validator = SQLValidator()

    @staticmethod
    def _quote_identifier(name: str) -> str:
        """Safely quote a SQLite table or column identifier."""
        return '"' + name.replace('"', '""') + '"'

    def discover_schema(self, connector: DataConnector) -> Dict[str, TableDetail]:
        """
        Discovers all tables, columns, data types, primary keys, and explicit foreign keys
        present in the active DataConnector in-memory SQLite database.
        """
        with connector._lock:
            conn = connector.get_connection()
            cursor = conn.cursor()

            # Find all user tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            table_names = [r[0] for r in cursor.fetchall()]

            tables: Dict[str, TableDetail] = {}

            for t_name in table_names:
                safe_table = self._quote_identifier(t_name)

                # 1. Total row count
                cursor.execute(f"SELECT COUNT(*) FROM {safe_table};")
                row_count = cursor.fetchone()[0]

                # 2. PRAGMA table_info (cid, name, type, notnull, dflt_value, pk)
                cursor.execute(f"PRAGMA table_info({safe_table});")
                col_infos = cursor.fetchall()

                # 3. PRAGMA foreign_key_list (id, seq, table, from, to, on_update, on_delete, match)
                cursor.execute(f"PRAGMA foreign_key_list({safe_table});")
                fk_rows = cursor.fetchall()
                fk_map: Dict[str, Tuple[str, str]] = {}
                for fk in fk_rows:
                    from_col = fk[3]
                    to_tbl = fk[2]
                    to_col = fk[4]
                    fk_map[from_col] = (to_tbl, to_col)

                # 4. PRAGMA index_list to find unique single-column indexes
                unique_cols: Set[str] = set()
                try:
                    cursor.execute(f"PRAGMA index_list({safe_table});")
                    idx_rows = cursor.fetchall()
                    for idx in idx_rows:
                        is_unique = bool(idx[2])
                        if is_unique:
                            idx_name = idx[1]
                            cursor.execute(f"PRAGMA index_info({self._quote_identifier(idx_name)});")
                            col_info_list = cursor.fetchall()
                            if len(col_info_list) == 1:
                                unique_cols.add(col_info_list[0][2])
                except Exception as e:
                    logger.debug(f"Index inspection skipped for {t_name}: {e}")

                columns: List[ColumnDetail] = []
                pks: List[str] = []

                for col in col_infos:
                    col_name = col[1]
                    declared_type = col[2] or "TEXT"
                    is_not_null = bool(col[3])
                    is_pk = bool(col[5] > 0)
                    if is_pk:
                        pks.append(col_name)

                    safe_col = self._quote_identifier(col_name)
                    null_count = 0
                    null_rate = 0.0
                    unique_count = 0
                    unique_rate = 0.0
                    sample_vals: List[Any] = []

                    if row_count > 0:
                        try:
                            # Null count
                            cursor.execute(f"SELECT COUNT(*) FROM {safe_table} WHERE {safe_col} IS NULL;")
                            null_count = cursor.fetchone()[0]
                            null_rate = round(null_count / row_count, 4)

                            # Distinct count
                            cursor.execute(f"SELECT COUNT(DISTINCT {safe_col}) FROM {safe_table} WHERE {safe_col} IS NOT NULL;")
                            unique_count = cursor.fetchone()[0]
                            non_null_rows = row_count - null_count
                            if non_null_rows > 0:
                                unique_rate = round(unique_count / non_null_rows, 4)

                            # Sample values
                            cursor.execute(f"SELECT {safe_col} FROM {safe_table} WHERE {safe_col} IS NOT NULL LIMIT 3;")
                            sample_vals = [r[0] for r in cursor.fetchall()]
                        except Exception as e:
                            logger.debug(f"Stats query failed for {t_name}.{col_name}: {e}")

                    # Foreign key info
                    is_fk = col_name in fk_map
                    fk_target_tbl = fk_map[col_name][0] if is_fk else None
                    fk_target_col = fk_map[col_name][1] if is_fk else None

                    col_detail = ColumnDetail(
                        name=col_name,
                        data_type=declared_type,
                        is_pk=is_pk,
                        is_fk=is_fk,
                        fk_target_table=fk_target_tbl,
                        fk_target_column=fk_target_col,
                        is_nullable=not is_not_null,
                        total_count=row_count,
                        null_count=null_count,
                        null_rate=null_rate,
                        unique_count=unique_count,
                        unique_rate=unique_rate,
                        sample_values=sample_vals
                    )
                    columns.append(col_detail)

                # Inferred primary key heuristic if none was explicitly declared in DDL
                if not pks and row_count > 0:
                    for c in columns:
                        # If named id or table_id, 0 nulls, and 100% unique
                        is_id_name = (
                            c.name.lower() in ("id", f"{t_name.lower()}_id", f"{singularize(t_name)}_id")
                            or c.name.lower().endswith("_id")
                        )
                        if is_id_name and c.null_count == 0 and c.unique_count == row_count:
                            c.is_pk = True
                            pks.append(c.name)
                            break

                tables[t_name] = TableDetail(
                    table_name=t_name,
                    row_count=row_count,
                    columns=columns,
                    primary_keys=pks
                )

            return tables

    def infer_relationships(
        self,
        connector: DataConnector,
        tables: Dict[str, TableDetail],
        session_id: Optional[str] = None,
        dataset_name: Optional[str] = None
    ) -> List[RelationshipDetail]:
        """
        Discovers explicit relationships and infers candidate relationships based on
        naming conventions, data types, uniqueness, and value overlaps.
        Merges persistent user confirmations/rejections from metadata_manager.
        """
        relationships: Dict[str, RelationshipDetail] = {}

        # 1. First, pull explicit foreign keys declared in database DDL
        for t_name, t_detail in tables.items():
            for col in t_detail.columns:
                if col.is_fk and col.fk_target_table and col.fk_target_column:
                    target_tbl = col.fk_target_table
                    target_col = col.fk_target_column
                    if target_tbl in tables:
                        # Determine cardinality
                        target_is_unique = any(
                            c.name == target_col and (c.is_pk or c.unique_rate == 1.0)
                            for c in tables[target_tbl].columns
                        )
                        source_is_unique = col.is_pk or (col.unique_rate == 1.0 and col.total_count > 0)

                        if source_is_unique and target_is_unique:
                            cardinality = "one-to-one"
                        elif target_is_unique:
                            cardinality = "one-to-many"
                        else:
                            cardinality = "many-to-many"

                        rel_id = f"{t_name}.{col.name}->{target_tbl}.{target_col}"
                        relationships[rel_id] = RelationshipDetail(
                            id=rel_id,
                            source_table=t_name,
                            source_column=col.name,
                            target_table=target_tbl,
                            target_column=target_col,
                            cardinality=cardinality,
                            status="confirmed",
                            confidence=1.0,
                            source="explicit_fk",
                            overlap_percentage=100.0,
                            overlap_count=col.unique_count,
                            sample_matches=col.sample_values[:3],
                            is_ambiguous=False,
                            ambiguity_note=None,
                            user_confirmed=True
                        )

        # 2. Heuristic candidate inference across all pairs of tables
        table_list = list(tables.keys())
        with connector._lock:
            conn = connector.get_connection()
            cursor = conn.cursor()

            for i, tbl_a in enumerate(table_list):
                for j, tbl_b in enumerate(table_list):
                    if i == j:
                        continue

                    detail_a = tables[tbl_a]
                    detail_b = tables[tbl_b]

                    for col_a in detail_a.columns:
                        for col_b in detail_b.columns:
                            # Skip if explicit FK already recorded this pair
                            direct_id = f"{tbl_a}.{col_a.name}->{tbl_b}.{col_b.name}"
                            reverse_id = f"{tbl_b}.{col_b.name}->{tbl_a}.{col_a.name}"
                            if direct_id in relationships or reverse_id in relationships:
                                continue

                            # Check type compatibility
                            if not is_type_compatible(col_a.data_type, col_b.data_type):
                                continue

                            # Check naming pattern heuristics
                            ca_lower = col_a.name.lower()
                            cb_lower = col_b.name.lower()
                            ta_lower = tbl_a.lower()
                            tb_lower = tbl_b.lower()
                            ta_sing = singularize(ta_lower)
                            tb_sing = singularize(tb_lower)

                            name_score = 0.0
                            is_name_match = False
                            candidate_source = None  # (child_tbl, child_col)
                            candidate_target = None  # (parent_tbl, parent_col)

                            # Pattern 1: tbl_b has customer_id pointing to customers.id
                            if cb_lower in (f"{ta_lower}_id", f"{ta_sing}_id") and ca_lower in ("id", f"{ta_lower}_id", f"{ta_sing}_id"):
                                name_score = 0.45
                                is_name_match = True
                                candidate_source = (tbl_b, col_b.name)
                                candidate_target = (tbl_a, col_a.name)

                            elif ca_lower in (f"{tb_lower}_id", f"{tb_sing}_id") and cb_lower in ("id", f"{tb_lower}_id", f"{tb_sing}_id"):
                                name_score = 0.45
                                is_name_match = True
                                candidate_source = (tbl_a, col_a.name)
                                candidate_target = (tbl_b, col_b.name)

                            # Pattern 2: Matching {entity}_id on both sides (e.g. user_id == user_id)
                            elif ca_lower == cb_lower and (ca_lower.endswith("_id") or ca_lower.endswith("_key") or ca_lower.endswith("_code") or ca_lower.endswith("_no")):
                                name_score = 0.40
                                is_name_match = True
                                # Decide source vs target based on PK or uniqueness
                                if col_a.is_pk or (col_a.unique_rate == 1.0 and col_a.total_count > 0):
                                    candidate_target = (tbl_a, col_a.name)
                                    candidate_source = (tbl_b, col_b.name)
                                elif col_b.is_pk or (col_b.unique_rate == 1.0 and col_b.total_count > 0):
                                    candidate_target = (tbl_b, col_b.name)
                                    candidate_source = (tbl_a, col_a.name)
                                else:
                                    candidate_source = (tbl_a, col_a.name)
                                    candidate_target = (tbl_b, col_b.name)

                            # Pattern 3: Exact column name match not in generic blacklist
                            elif ca_lower == cb_lower and ca_lower not in GENERIC_COLUMN_NAMES:
                                name_score = 0.25
                                is_name_match = True
                                if col_a.is_pk or col_a.unique_rate == 1.0:
                                    candidate_target = (tbl_a, col_a.name)
                                    candidate_source = (tbl_b, col_b.name)
                                else:
                                    candidate_source = (tbl_a, col_a.name)
                                    candidate_target = (tbl_b, col_b.name)

                            if not is_name_match or not candidate_source or not candidate_target:
                                continue

                            src_tbl, src_col = candidate_source
                            tgt_tbl, tgt_col = candidate_target
                            src_col_obj = next((c for c in tables[src_tbl].columns if c.name == src_col), None)
                            tgt_col_obj = next((c for c in tables[tgt_tbl].columns if c.name == tgt_col), None)

                            if not src_col_obj or not tgt_col_obj:
                                continue

                            rel_id = f"{src_tbl}.{src_col}->{tgt_tbl}.{tgt_col}"
                            if rel_id in relationships:
                                continue

                            # Value Overlap Analysis
                            overlap_count = 0
                            overlap_pct = 0.0
                            sample_matches = []

                            safe_src_t = self._quote_identifier(src_tbl)
                            safe_src_c = self._quote_identifier(src_col)
                            safe_tgt_t = self._quote_identifier(tgt_tbl)
                            safe_tgt_c = self._quote_identifier(tgt_col)

                            if tables[src_tbl].row_count > 0 and tables[tgt_tbl].row_count > 0:
                                try:
                                    cursor.execute(f"""
                                        SELECT COUNT(DISTINCT s)
                                        FROM (SELECT {safe_src_c} AS s FROM {safe_src_t} WHERE {safe_src_c} IS NOT NULL)
                                        WHERE s IN (SELECT {safe_tgt_c} FROM {safe_tgt_t} WHERE {safe_tgt_c} IS NOT NULL);
                                    """)
                                    overlap_count = cursor.fetchone()[0]

                                    denom = min(src_col_obj.unique_count, tgt_col_obj.unique_count)
                                    if denom > 0:
                                        overlap_pct = round((overlap_count / denom) * 100.0, 1)

                                    # Sample matches
                                    cursor.execute(f"""
                                        SELECT DISTINCT s
                                        FROM (SELECT {safe_src_c} AS s FROM {safe_src_t} WHERE {safe_src_c} IS NOT NULL)
                                        WHERE s IN (SELECT {safe_tgt_c} FROM {safe_tgt_t} WHERE {safe_tgt_c} IS NOT NULL)
                                        LIMIT 3;
                                    """)
                                    sample_matches = [r[0] for r in cursor.fetchall()]
                                except Exception as e:
                                    logger.debug(f"Overlap query failed for {rel_id}: {e}")

                            # Cardinality determination
                            tgt_is_unique = tgt_col_obj.is_pk or (tgt_col_obj.unique_rate == 1.0 and tgt_col_obj.total_count > 0)
                            src_is_unique = src_col_obj.is_pk or (src_col_obj.unique_rate == 1.0 and src_col_obj.total_count > 0)

                            if tgt_is_unique and src_is_unique:
                                cardinality = "one-to-one"
                            elif tgt_is_unique:
                                cardinality = "one-to-many"
                            else:
                                cardinality = "many-to-many"

                            # Confidence Scoring
                            type_score = 0.20
                            uniqueness_score = 0.20 if tgt_is_unique else 0.05
                            overlap_score = (overlap_pct / 100.0) * 0.25

                            # Penalty if empty or 0 overlap
                            if tables[src_tbl].row_count > 0 and tables[tgt_tbl].row_count > 0 and overlap_count == 0:
                                overlap_score = -0.20

                            # Null rate penalty on target
                            null_penalty = 0.15 if tgt_col_obj.null_rate > 0.3 else 0.0

                            confidence = round(max(0.0, min(0.98, name_score + type_score + uniqueness_score + overlap_score - null_penalty)), 2)

                            # Threshold for candidate inclusion: >= 0.40
                            if confidence >= 0.40:
                                relationships[rel_id] = RelationshipDetail(
                                    id=rel_id,
                                    source_table=src_tbl,
                                    source_column=src_col,
                                    target_table=tgt_tbl,
                                    target_column=tgt_col,
                                    cardinality=cardinality,
                                    status="inferred",
                                    confidence=confidence,
                                    source="inferred",
                                    overlap_percentage=overlap_pct,
                                    overlap_count=overlap_count,
                                    sample_matches=sample_matches,
                                    is_ambiguous=False,
                                    ambiguity_note=None,
                                    user_confirmed=False
                                )

        # 3. Detect ambiguous relationships (multiple candidate targets for same source column)
        src_groups: Dict[Tuple[str, str], List[RelationshipDetail]] = {}
        for rel in relationships.values():
            key = (rel.source_table, rel.source_column)
            src_groups.setdefault(key, []).append(rel)

        for (src_t, src_c), group in src_groups.items():
            if len(group) > 1:
                target_names = [f"{r.target_table}.{r.target_column} ({r.confidence * 100:.0f}%)" for r in group]
                for r in group:
                    r.is_ambiguous = True
                    r.ambiguity_note = f"Ambiguous join: matches multiple candidate tables ({', '.join(target_names)})"

        # 4. Merge persistent overrides (confirmed, rejected, custom) from metadata_manager
        if session_id:
            try:
                overrides = metadata_manager.get_schema_relationships(session_id, dataset_name)
                for ov in overrides:
                    src_t = ov["source_table"]
                    src_c = ov["source_column"]
                    tgt_t = ov["target_table"]
                    tgt_c = ov["target_column"]
                    ov_status = ov["status"]
                    ov_card = ov.get("cardinality") or "one-to-many"
                    rel_id = f"{src_t}.{src_c}->{tgt_t}.{tgt_c}"

                    if rel_id in relationships:
                        rel = relationships[rel_id]
                        rel.status = ov_status
                        rel.cardinality = ov_card
                        if ov_status == "confirmed":
                            rel.user_confirmed = True
                            rel.confidence = 1.0
                        elif ov_status == "rejected":
                            rel.user_rejected = True
                    else:
                        # User-created custom relationship
                        relationships[rel_id] = RelationshipDetail(
                            id=rel_id,
                            source_table=src_t,
                            source_column=src_c,
                            target_table=tgt_t,
                            target_column=tgt_c,
                            cardinality=ov_card,
                            status=ov_status,
                            confidence=1.0 if ov_status == "confirmed" else 0.5,
                            source="user_custom",
                            overlap_percentage=100.0,
                            overlap_count=0,
                            sample_matches=[],
                            is_ambiguous=False,
                            ambiguity_note=None,
                            user_confirmed=(ov_status == "confirmed"),
                            user_rejected=(ov_status == "rejected")
                        )
            except Exception as e:
                logger.error(f"Error loading persisted relationship overrides: {e}")

        # Return sorted list (confirmed first, then highest confidence inferred)
        status_order = {"confirmed": 0, "inferred": 1, "rejected": 2}
        sorted_rels = sorted(
            relationships.values(),
            key=lambda r: (status_order.get(r.status, 3), -r.confidence, r.source_table, r.target_table)
        )
        return sorted_rels

    def generate_join_sql(
        self,
        connector: DataConnector,
        table_a: str,
        table_b: str,
        join_type: str = "INNER JOIN",
        source_column: Optional[str] = None,
        target_column: Optional[str] = None,
        relationships: Optional[List[RelationshipDetail]] = None
    ) -> Dict[str, Any]:
        """
        Generates and validates an executable, dialect-accurate SQLite JOIN query.
        Guarantees safe quoting, handles ambiguous join paths, and validates execution safety.
        """
        schema = self.discover_schema(connector)
        if table_a not in schema:
            raise ValueError(f"Table '{table_a}' not found in active dataset.")
        if table_b not in schema:
            raise ValueError(f"Table '{table_b}' not found in active dataset.")

        clean_join_type = join_type.upper().strip()
        allowed_joins = {"INNER JOIN", "LEFT JOIN", "CROSS JOIN"}
        if clean_join_type not in allowed_joins:
            clean_join_type = "INNER JOIN"

        join_cond = ""
        is_ambiguous = False
        matching_rels: List[RelationshipDetail] = []
        explanation = ""

        # Direct explicit join columns provided
        if source_column and target_column:
            # Verify columns exist in the tables
            cols_a = [c.name for c in schema[table_a].columns]
            cols_b = [c.name for c in schema[table_b].columns]

            if source_column in cols_a and target_column in cols_b:
                col_a = source_column
                col_b = target_column
            elif source_column in cols_b and target_column in cols_a:
                col_a = target_column
                col_b = source_column
            else:
                raise ValueError(
                    f"Columns '{source_column}' and '{target_column}' do not match tables '{table_a}' and '{table_b}'."
                )

            safe_ta = self._quote_identifier(table_a)
            safe_tb = self._quote_identifier(table_b)
            safe_ca = self._quote_identifier(col_a)
            safe_cb = self._quote_identifier(col_b)
            join_cond = f"{safe_ta}.{safe_ca} = {safe_tb}.{safe_cb}"
            explanation = f"Joined on custom condition {table_a}.{col_a} = {table_b}.{col_b}"

        else:
            # Find candidate relationships between table_a and table_b
            if relationships is None:
                relationships = self.infer_relationships(connector, schema)

            matching_rels = [
                r for r in relationships
                if r.status != "rejected" and (
                    (r.source_table == table_a and r.target_table == table_b) or
                    (r.source_table == table_b and r.target_table == table_a)
                )
            ]

            if not matching_rels:
                raise ValueError(
                    f"No active relationship found between '{table_a}' and '{table_b}'. "
                    f"Please confirm an inferred relationship or specify join columns."
                )

            if len(matching_rels) > 1:
                is_ambiguous = True

            chosen_rel = matching_rels[0]
            src_t = chosen_rel.source_table
            src_c = chosen_rel.source_column
            tgt_t = chosen_rel.target_table
            tgt_c = chosen_rel.target_column

            safe_src_t = self._quote_identifier(src_t)
            safe_src_c = self._quote_identifier(src_c)
            safe_tgt_t = self._quote_identifier(tgt_t)
            safe_tgt_c = self._quote_identifier(tgt_c)

            join_cond = f"{safe_src_t}.{safe_src_c} = {safe_tgt_t}.{safe_tgt_c}"
            status_desc = "confirmed" if chosen_rel.status == "confirmed" else f"inferred ({chosen_rel.confidence * 100:.0f}% confidence)"
            explanation = (
                f"Joined using {status_desc} {chosen_rel.cardinality} relationship: "
                f"{src_t}.{src_c} = {tgt_t}.{tgt_c}"
            )

        # Build column selections with table qualifications
        col_selects = []
        for c in schema[table_a].columns:
            col_selects.append(f"{self._quote_identifier(table_a)}.{self._quote_identifier(c.name)}")
        for c in schema[table_b].columns:
            # If same column name, alias it to avoid duplicate name ambiguity
            c_name = c.name
            if any(ca.name == c_name for ca in schema[table_a].columns):
                col_selects.append(
                    f"{self._quote_identifier(table_b)}.{self._quote_identifier(c_name)} AS {self._quote_identifier(f'{table_b}_{c_name}')}"
                )
            else:
                col_selects.append(f"{self._quote_identifier(table_b)}.{self._quote_identifier(c_name)}")

        sql = (
            f"SELECT\n    " + ",\n    ".join(col_selects) + "\n"
            f"FROM {self._quote_identifier(table_a)}\n"
            f"{clean_join_type} {self._quote_identifier(table_b)}\n"
            f"    ON {join_cond}\n"
            f"LIMIT 100;"
        )

        # Validate SQL against database engine
        with connector._lock:
            conn = connector.get_connection()
            val_res = self.sql_validator.validate(sql, conn)
            if not val_res.is_valid:
                logger.error(f"Generated JOIN SQL failed validation: {val_res.message}\nSQL: {sql}")
                raise ValueError(f"Generated SQL failed validation: {val_res.message}")

        return {
            "sql": sql,
            "table_a": table_a,
            "table_b": table_b,
            "join_type": clean_join_type,
            "join_condition": join_cond,
            "explanation": explanation,
            "is_ambiguous": is_ambiguous,
            "available_relationships": [r.to_dict() for r in matching_rels]
        }


# Global singleton instance
schema_engine = RelationalSchemaEngine()
