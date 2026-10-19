"""
query_history.py - Persistent Query History & Session Memory

Stores and retrieves natural-language to SQL execution history using DataVerse's
persistent SQLite metadata manager (`dataverse_meta.db`).
Supports multi-turn context extraction and dataset-specific filtering with
strict session isolation.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import logging
from pathlib import Path

from metadata_manager import MetadataManager, metadata_manager as default_metadata_mgr

logger = logging.getLogger("dataverse.history")


@dataclass
class HistoryEntry:
    id: Optional[int]
    timestamp: str
    dataset_name: str
    question: str
    sql_query: str
    success: bool
    row_count: int
    execution_time: float
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QueryHistory:
    """
    Thread-safe query history manager backed by MetadataManager (`dataverse_meta.db`).
    Guarantees session isolation when session_id is provided.
    """
    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        session_id: str = "default",
        mgr: Optional[MetadataManager] = None
    ):
        self.session_id = session_id or "default"
        self.db_path = str(db_path) if db_path else None
        if mgr:
            self._mgr = mgr
        elif db_path:
            self._mgr = MetadataManager(db_path=db_path)
        else:
            self._mgr = default_metadata_mgr

    def add_entry(
        self,
        question: str,
        sql_query: str,
        success: bool,
        row_count: int = 0,
        execution_time: float = 0.0,
        error_message: str = "",
        dataset_name: str = ""
    ) -> int:
        """Adds a new record to the query history for this session."""
        return self._mgr.add_history_entry(
            session_id=self.session_id,
            question=question,
            sql_query=sql_query,
            success=success,
            row_count=row_count,
            execution_time=execution_time,
            error_message=error_message,
            dataset_name=dataset_name
        )

    def get_recent(
        self,
        limit: int = 50,
        dataset_name: Optional[str] = None,
        search: Optional[str] = None,
        status_filter: Optional[str] = None
    ) -> List[HistoryEntry]:
        """Retrieves recent query history records for this session."""
        records = self._mgr.get_history_entries(
            session_id=self.session_id,
            limit=limit,
            dataset_name=dataset_name,
            search=search,
            status_filter=status_filter
        )
        return [
            HistoryEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                dataset_name=r["dataset_name"],
                question=r["question"],
                sql_query=r["sql_query"],
                success=r["success"],
                row_count=r["row_count"],
                execution_time=r["execution_time"],
                error_message=r["error_message"]
            )
            for r in records
        ]

    def clear_history(self, dataset_name: Optional[str] = None) -> bool:
        """Clears query history for this session."""
        return self._mgr.clear_history(session_id=self.session_id, dataset_name=dataset_name)

    def delete_entry(self, entry_id: int) -> bool:
        """Deletes a specific history entry by ID within this session."""
        return self._mgr.delete_history_entry(session_id=self.session_id, entry_id=entry_id)

    def get_recent_context(self, limit: int = 3, dataset_name: Optional[str] = None) -> str:
        """Formats recent successful queries into a multi-turn conversation context."""
        recent = self.get_recent(limit=limit, dataset_name=dataset_name)
        successful = [e for e in recent if e.success and e.sql_query]
        if not successful:
            return ""

        # Chronological order
        successful.reverse()
        lines = ["Recent Successful Queries in this Session:"]
        for entry in successful:
            lines.append(f"- Question: {entry.question}")
            lines.append(f"  SQL: {entry.sql_query}")
        return "\n".join(lines)
