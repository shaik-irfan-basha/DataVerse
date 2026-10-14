"""
query_history.py - Persistent Query History & Session Memory

Stores and retrieves natural-language to SQL execution history using a local SQLite database.
Supports multi-turn context extraction and dataset-specific filtering.
"""

import sqlite3
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import os

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
    Thread-safe SQLite-backed query history manager.
    """
    def __init__(self, db_path: str = "dataverse_history.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes the history database schema."""
        with self._lock:
            # Ensure parent directory exists if path contains directories
            dir_name = os.path.dirname(self.db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS query_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        dataset_name TEXT DEFAULT '',
                        question TEXT NOT NULL,
                        sql_query TEXT DEFAULT '',
                        success INTEGER NOT NULL,
                        row_count INTEGER DEFAULT 0,
                        execution_time REAL DEFAULT 0.0,
                        error_message TEXT DEFAULT ''
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_history_timestamp 
                    ON query_history (timestamp DESC);
                """)
                conn.commit()

    def add_entry(self, 
                  question: str, 
                  sql_query: str, 
                  success: bool, 
                  row_count: int = 0, 
                  execution_time: float = 0.0, 
                  error_message: str = "",
                  dataset_name: str = "") -> int:
        """
        Adds a new record to the query history.
        Returns the inserted record's id.
        """
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        INSERT INTO query_history (
                            timestamp, dataset_name, question, sql_query,
                            success, row_count, execution_time, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp_str,
                        dataset_name or "",
                        question,
                        sql_query or "",
                        1 if success else 0,
                        row_count,
                        round(execution_time, 4),
                        error_message or ""
                    ))
                    conn.commit()
                    return cursor.lastrowid
            except Exception as e:
                logger.error(f"Failed to record query history: {e}")
                return -1

    def get_recent(self, limit: int = 50, dataset_name: Optional[str] = None) -> List[HistoryEntry]:
        """
        Retrieves the most recent query history entries.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    if dataset_name:
                        cursor = conn.execute("""
                            SELECT id, timestamp, dataset_name, question, sql_query,
                                   success, row_count, execution_time, error_message
                            FROM query_history
                            WHERE dataset_name = ?
                            ORDER BY id DESC
                            LIMIT ?
                        """, (dataset_name, limit))
                    else:
                        cursor = conn.execute("""
                            SELECT id, timestamp, dataset_name, question, sql_query,
                                   success, row_count, execution_time, error_message
                            FROM query_history
                            ORDER BY id DESC
                            LIMIT ?
                        """, (limit,))
                    
                    rows = cursor.fetchall()
                    return [
                        HistoryEntry(
                            id=row["id"],
                            timestamp=row["timestamp"],
                            dataset_name=row["dataset_name"],
                            question=row["question"],
                            sql_query=row["sql_query"],
                            success=bool(row["success"]),
                            row_count=row["row_count"],
                            execution_time=row["execution_time"],
                            error_message=row["error_message"]
                        )
                        for row in rows
                    ]
            except Exception as e:
                logger.error(f"Failed to retrieve query history: {e}")
                return []

    def clear_history(self, dataset_name: Optional[str] = None) -> bool:
        """
        Clears query history (optionally filtered by dataset).
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    if dataset_name:
                        conn.execute("DELETE FROM query_history WHERE dataset_name = ?", (dataset_name,))
                    else:
                        conn.execute("DELETE FROM query_history")
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to clear query history: {e}")
                return False

    def delete_entry(self, entry_id: int) -> bool:
        """Deletes a specific history entry by ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM query_history WHERE id = ?", (entry_id,))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to delete history entry {entry_id}: {e}")
                return False

    def get_recent_context(self, limit: int = 3, dataset_name: Optional[str] = None) -> str:
        """
        Formats recent successful queries into a multi-turn conversation context
        suitable for feeding into prompt builder.
        """
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
