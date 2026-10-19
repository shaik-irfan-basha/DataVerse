"""
metadata_manager.py - Persistent SQLite Metadata Store for DataVerse

Manages local metadata persistence for DataVerse:
- Version-controlled schema migrations
- Session metadata and rehydration across server restarts
- Session-isolated query history with search and status filtering
- Session-isolated saved queries (bookmarks)
- Session-isolated user preferences
- Zero persistence of secrets (API keys, authorization tokens)
- Resilient error handling (WAL mode, busy timeout, corruption backup & recovery)
"""

import os
import sqlite3
import threading
import time
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger("dataverse.metadata")
from paths import get_metadata_db_path

DEFAULT_DB_PATH = get_metadata_db_path()



class MetadataCorruptionError(Exception):
    """Raised when SQLite database corruption is detected."""
    pass


class MetadataMigrationError(Exception):
    """Raised when schema migration fails."""
    pass


class MetadataManager:
    """
    Thread-safe, robust SQLite metadata manager for DataVerse.
    Enforces session isolation across history, saved queries, and preferences.
    """
    CURRENT_VERSION = 2

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path or os.getenv("DATAVERSE_META_DB", DEFAULT_DB_PATH))
        self._lock = threading.RLock()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a connection configured with WAL mode and row factory."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable write-ahead logging for high concurrency and resilience
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
        except sqlite3.Error as e:
            logger.warning(f"Could not apply SQLite PRAGMAs: {e}")
        return conn

    def _init_database(self):
        """Initializes database directory, verifies integrity, and runs migrations."""
        with self._lock:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Check database integrity if file already exists and has size
            if self.db_path.exists() and self.db_path.stat().st_size > 0:
                if not self._check_integrity():
                    logger.error(f"Integrity check failed for {self.db_path}. Recovering...")
                    self._recover_corrupted_db()

            # Execute schema migrations
            self._apply_migrations()

    def _check_integrity(self) -> bool:
        """Runs PRAGMA quick_check to verify database health."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            cursor = conn.execute("PRAGMA quick_check;")
            row = cursor.fetchone()
            return bool(row and row[0] == "ok")
        except Exception as e:
            logger.error(f"Error checking database integrity: {e}")
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _recover_corrupted_db(self):
        """Backs up corrupted database to timestamped file and initializes a fresh database."""
        import gc
        gc.collect()
        timestamp = int(time.time())
        corrupt_backup = self.db_path.with_name(f"{self.db_path.name}.corrupt.{timestamp}")
        try:
            shutil.move(str(self.db_path), str(corrupt_backup))
            logger.warning(f"Moved corrupted metadata database to {corrupt_backup}")
        except Exception as e:
            logger.error(f"Failed to move corrupted database {self.db_path}: {e}")
            # Try removing if move failed
            try:
                self.db_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _apply_migrations(self):
        """Applies versioned schema migrations inside atomic transactions."""
        with self._get_connection() as conn:
            # Create migrations tracking table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT NOT NULL
                );
            """)
            conn.commit()

            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations;")
            row = cursor.fetchone()
            current_version = row[0] if (row and row[0] is not None) else 0

            if current_version < 1:
                self._migrate_to_v1(conn)
            if current_version < 2:
                self._migrate_to_v2(conn)

    def _migrate_to_v1(self, conn: sqlite3.Connection):
        """Migration 1: Core tables for sessions, history, saved queries, preferences."""
        logger.info("Applying metadata migration version 1...")
        try:
            # 1. Sessions table (tracks session metadata across server restarts; NO SECRETS)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    dataset_name TEXT DEFAULT ''
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);")

            # 2. Query History table (isolated by session_id)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    dataset_name TEXT DEFAULT '',
                    question TEXT NOT NULL,
                    sql_query TEXT DEFAULT '',
                    success INTEGER NOT NULL DEFAULT 1,
                    row_count INTEGER DEFAULT 0,
                    execution_time REAL DEFAULT 0.0,
                    error_message TEXT DEFAULT ''
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_session_ts ON query_history(session_id, timestamp DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_session_dataset ON query_history(session_id, dataset_name);")

            # 3. Saved Queries / Bookmarks table (isolated by session_id)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    question TEXT DEFAULT '',
                    sql_query TEXT NOT NULL,
                    dataset_name TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    notes TEXT DEFAULT ''
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_queries_session ON saved_queries(session_id, created_at DESC);")

            # 4. User Preferences table (isolated by session_id; key-value)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    session_id TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    pref_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, pref_key)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_prefs_session ON user_preferences(session_id);")

            # Record migration
            conn.execute("""
                INSERT INTO schema_migrations (version, applied_at, description)
                VALUES (1, ?, 'Initial metadata schema: sessions, query_history, saved_queries, user_preferences');
            """, (datetime.utcnow().isoformat(),))
            conn.commit()
            logger.info("Successfully applied metadata migration version 1.")
        except Exception as e:
            conn.rollback()
            raise MetadataMigrationError(f"Migration version 1 failed: {e}") from e

    def _migrate_to_v2(self, conn: sqlite3.Connection):
        """Migration 2: Relational schema relationships table (confirmed, rejected, custom)."""
        logger.info("Applying metadata migration version 2...")
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    dataset_name TEXT DEFAULT '',
                    source_table TEXT NOT NULL,
                    source_column TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    target_column TEXT NOT NULL,
                    status TEXT NOT NULL, -- 'confirmed', 'rejected', 'custom'
                    cardinality TEXT DEFAULT 'one-to-many',
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, dataset_name, source_table, source_column, target_table, target_column)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_session ON schema_relationships(session_id, dataset_name);")

            # Record migration
            conn.execute("""
                INSERT INTO schema_migrations (version, applied_at, description)
                VALUES (2, ?, 'Relational schema relationships management');
            """, (datetime.utcnow().isoformat(),))
            conn.commit()
            logger.info("Successfully applied metadata migration version 2.")
        except Exception as e:
            conn.rollback()
            raise MetadataMigrationError(f"Migration version 2 failed: {e}") from e

    # =========================================================================
    # Secret Exclusion Guard
    # =========================================================================

    @staticmethod
    def _assert_no_secrets(value: Any):
        """Raises ValueError if any API key or secret format is detected in payload."""
        if not value:
            return
        val_str = str(value)
        # Block Groq, Together, OpenAI, Anthropic key prefixes
        forbidden_prefixes = ["gsk_", "Bearer ", "sk-", "eyJ"]
        for prefix in forbidden_prefixes:
            if prefix.lower() in val_str.lower():
                raise ValueError(f"Secret detected in persistent metadata payload. Persistence aborted for security.")

    # =========================================================================
    # Session Persistence & Rehydration Methods
    # =========================================================================

    def upsert_session(self, session_id: str, token_hash: str, created_at: float, last_accessed: float, dataset_name: str = "") -> bool:
        """Persists or updates an authenticated session metadata record."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO sessions (session_id, token_hash, created_at, last_accessed, dataset_name)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(session_id) DO UPDATE SET
                            last_accessed = excluded.last_accessed,
                            dataset_name = CASE WHEN excluded.dataset_name != '' THEN excluded.dataset_name ELSE sessions.dataset_name END;
                    """, (session_id, token_hash, created_at, last_accessed, dataset_name or ""))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error persisting session {session_id}: {e}")
                return False

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieves session record by hashed token for rehydration across server restarts."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT session_id, token_hash, created_at, last_accessed, dataset_name
                        FROM sessions
                        WHERE token_hash = ?;
                    """, (token_hash,))
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
                    return None
            except Exception as e:
                logger.error(f"Error querying session by token hash: {e}")
                return None

    def touch_session(self, session_id: str, last_accessed: Optional[float] = None) -> bool:
        """Refreshes last_accessed timestamp in database."""
        now = last_accessed if last_accessed is not None else time.time()
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("UPDATE sessions SET last_accessed = ? WHERE session_id = ?;", (now, session_id))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error touching session {session_id}: {e}")
                return False

    def update_session_dataset(self, session_id: str, dataset_name: str) -> bool:
        """Updates the active dataset associated with the session."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("UPDATE sessions SET dataset_name = ? WHERE session_id = ?;", (dataset_name or "", session_id))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error updating dataset for session {session_id}: {e}")
                return False

    def cleanup_expired_sessions(self, ttl_seconds: int) -> int:
        """Deletes sessions whose last_accessed age exceeds ttl_seconds."""
        cutoff = time.time() - ttl_seconds
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("DELETE FROM sessions WHERE last_accessed < ?;", (cutoff,))
                    conn.commit()
                    return cursor.rowcount
            except Exception as e:
                logger.error(f"Error cleaning expired sessions: {e}")
                return 0

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session record and associated schema relationships."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
                    conn.execute("DELETE FROM schema_relationships WHERE session_id = ?;", (session_id,))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error deleting session {session_id}: {e}")
                return False

    # =========================================================================
    # Query History Methods (Strict Session Isolation)
    # =========================================================================

    def add_history_entry(
        self,
        session_id: str,
        question: str,
        sql_query: str,
        success: bool,
        row_count: int = 0,
        execution_time: float = 0.0,
        error_message: str = "",
        dataset_name: str = ""
    ) -> int:
        """Adds a new query execution record tied strictly to session_id."""
        self._assert_no_secrets(question)
        self._assert_no_secrets(sql_query)
        self._assert_no_secrets(error_message)

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        INSERT INTO query_history (
                            session_id, timestamp, dataset_name, question, sql_query,
                            success, row_count, execution_time, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        session_id,
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
                logger.error(f"Failed to record query history for session {session_id}: {e}")
                return -1

    def get_history_entries(
        self,
        session_id: str,
        limit: int = 50,
        dataset_name: Optional[str] = None,
        search: Optional[str] = None,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves query history records isolated strictly to session_id.
        Supports dataset filtering, text search (question & SQL), and status filtering.
        """
        query_parts = ["SELECT id, timestamp, dataset_name, question, sql_query, success, row_count, execution_time, error_message FROM query_history WHERE session_id = ?"]
        params: List[Any] = [session_id]

        if dataset_name:
            query_parts.append("AND dataset_name = ?")
            params.append(dataset_name)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query_parts.append("AND (question LIKE ? OR sql_query LIKE ? OR dataset_name LIKE ?)")
            params.extend([term, term, term])

        if status_filter:
            s = status_filter.lower().strip()
            if s == "success":
                query_parts.append("AND success = 1")
            elif s == "failed" or s == "error":
                query_parts.append("AND success = 0")

        query_parts.append("ORDER BY id DESC LIMIT ?")
        params.append(limit)

        sql = " ".join(query_parts)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute(sql, tuple(params))
                    rows = cursor.fetchall()
                    return [
                        {
                            "id": r["id"],
                            "timestamp": r["timestamp"],
                            "dataset_name": r["dataset_name"],
                            "question": r["question"],
                            "sql_query": r["sql_query"],
                            "success": bool(r["success"]),
                            "row_count": r["row_count"],
                            "execution_time": r["execution_time"],
                            "error_message": r["error_message"]
                        }
                        for r in rows
                    ]
            except Exception as e:
                logger.error(f"Failed to retrieve query history for session {session_id}: {e}")
                return []

    def get_history_entry(self, session_id: str, entry_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single history entry ensuring it belongs to session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT id, timestamp, dataset_name, question, sql_query, success, row_count, execution_time, error_message
                        FROM query_history
                        WHERE session_id = ? AND id = ?;
                    """, (session_id, entry_id))
                    row = cursor.fetchone()
                    if row:
                        return {
                            "id": row["id"],
                            "timestamp": row["timestamp"],
                            "dataset_name": row["dataset_name"],
                            "question": row["question"],
                            "sql_query": row["sql_query"],
                            "success": bool(row["success"]),
                            "row_count": row["row_count"],
                            "execution_time": row["execution_time"],
                            "error_message": row["error_message"]
                        }
                    return None
            except Exception as e:
                logger.error(f"Failed to retrieve history entry {entry_id} for session {session_id}: {e}")
                return None

    def delete_history_entry(self, session_id: str, entry_id: int) -> bool:
        """Deletes a specific history record strictly within session_id (idempotent)."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM query_history WHERE session_id = ? AND id = ?;", (session_id, entry_id))
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"Failed to delete history entry {entry_id} for session {session_id}: {e}")
                return False

    def clear_history(self, session_id: str, dataset_name: Optional[str] = None) -> bool:
        """Clears query history strictly within session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    if dataset_name:
                        conn.execute("DELETE FROM query_history WHERE session_id = ? AND dataset_name = ?;", (session_id, dataset_name))
                    else:
                        conn.execute("DELETE FROM query_history WHERE session_id = ?;", (session_id,))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to clear history for session {session_id}: {e}")
                return False

    # =========================================================================
    # Saved Queries (Bookmarks) Methods (Strict Session Isolation)
    # =========================================================================

    def save_query(
        self,
        session_id: str,
        title: str,
        sql_query: str,
        question: str = "",
        dataset_name: str = "",
        notes: str = ""
    ) -> int:
        """Saves a query bookmark tied strictly to session_id."""
        self._assert_no_secrets(title)
        self._assert_no_secrets(sql_query)
        self._assert_no_secrets(question)
        self._assert_no_secrets(notes)

        created_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        INSERT INTO saved_queries (
                            session_id, title, question, sql_query, dataset_name, created_at, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """, (
                        session_id,
                        title.strip() or "Untitled Query",
                        question.strip() if question else "",
                        sql_query.strip(),
                        dataset_name.strip() if dataset_name else "",
                        created_at_str,
                        notes.strip() if notes else ""
                    ))
                    conn.commit()
                    return cursor.lastrowid
            except Exception as e:
                logger.error(f"Failed to save query bookmark for session {session_id}: {e}")
                return -1

    def get_saved_queries(
        self,
        session_id: str,
        dataset_name: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves saved query bookmarks strictly for session_id."""
        query_parts = ["SELECT id, session_id, title, question, sql_query, dataset_name, created_at, notes FROM saved_queries WHERE session_id = ?"]
        params: List[Any] = [session_id]

        if dataset_name:
            query_parts.append("AND dataset_name = ?")
            params.append(dataset_name)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query_parts.append("AND (title LIKE ? OR question LIKE ? OR sql_query LIKE ? OR notes LIKE ?)")
            params.extend([term, term, term, term])

        query_parts.append("ORDER BY id DESC")
        sql = " ".join(query_parts)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute(sql, tuple(params))
                    rows = cursor.fetchall()
                    return [
                        {
                            "id": r["id"],
                            "session_id": r["session_id"],
                            "title": r["title"],
                            "question": r["question"],
                            "sql_query": r["sql_query"],
                            "dataset_name": r["dataset_name"],
                            "created_at": r["created_at"],
                            "notes": r["notes"]
                        }
                        for r in rows
                    ]
            except Exception as e:
                logger.error(f"Failed to retrieve saved queries for session {session_id}: {e}")
                return []

    def get_saved_query(self, session_id: str, query_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single saved query bookmark ensuring it belongs to session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT id, session_id, title, question, sql_query, dataset_name, created_at, notes
                        FROM saved_queries
                        WHERE session_id = ? AND id = ?;
                    """, (session_id, query_id))
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
                    return None
            except Exception as e:
                logger.error(f"Failed to get saved query {query_id} for session {session_id}: {e}")
                return None

    def delete_saved_query(self, session_id: str, query_id: int) -> bool:
        """Deletes a saved query bookmark strictly within session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("DELETE FROM saved_queries WHERE session_id = ? AND id = ?;", (session_id, query_id))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to delete saved query {query_id} for session {session_id}: {e}")
                return False

    # =========================================================================
    # User Preferences Methods (Strict Session Isolation; No Secrets)
    # =========================================================================

    def set_preference(self, session_id: str, key: str, value: str) -> bool:
        """Persists a user preference key-value pair strictly for session_id."""
        self._assert_no_secrets(key)
        self._assert_no_secrets(value)

        updated_at = datetime.utcnow().isoformat()
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO user_preferences (session_id, pref_key, pref_value, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(session_id, pref_key) DO UPDATE SET
                            pref_value = excluded.pref_value,
                            updated_at = excluded.updated_at;
                    """, (session_id, key.strip(), str(value), updated_at))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to set preference '{key}' for session {session_id}: {e}")
                return False

    def get_preference(self, session_id: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieves a single user preference value strictly for session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT pref_value FROM user_preferences WHERE session_id = ? AND pref_key = ?;
                    """, (session_id, key.strip()))
                    row = cursor.fetchone()
                    if row:
                        return row[0]
                    return default
            except Exception as e:
                logger.error(f"Failed to get preference '{key}' for session {session_id}: {e}")
                return default

    def get_all_preferences(self, session_id: str) -> Dict[str, str]:
        """Retrieves all user preferences strictly for session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT pref_key, pref_value FROM user_preferences WHERE session_id = ?;
                    """, (session_id,))
                    rows = cursor.fetchall()
                    return {r["pref_key"]: r["pref_value"] for r in rows}
            except Exception as e:
                logger.error(f"Failed to get all preferences for session {session_id}: {e}")
                return {}

    def delete_preference(self, session_id: str, key: str) -> bool:
        """Deletes a preference key strictly for session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("DELETE FROM user_preferences WHERE session_id = ? AND pref_key = ?;", (session_id, key.strip()))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to delete preference '{key}' for session {session_id}: {e}")
                return False

    # =========================================================================
    # Relational Schema Relationships Methods (Phase 4, Strict Session Isolation)
    # =========================================================================

    def save_schema_relationship(
        self,
        session_id: str,
        dataset_name: str,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        status: str,  # 'confirmed', 'rejected', 'custom'
        cardinality: str = "one-to-many"
    ) -> bool:
        """Saves or updates a relationship override (confirmed/rejected/custom) strictly for session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    created_at = datetime.utcnow().isoformat()
                    conn.execute("""
                        INSERT INTO schema_relationships (
                            session_id, dataset_name, source_table, source_column,
                            target_table, target_column, status, cardinality, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, dataset_name, source_table, source_column, target_table, target_column)
                        DO UPDATE SET
                            status = excluded.status,
                            cardinality = excluded.cardinality,
                            created_at = excluded.created_at;
                    """, (
                        session_id, dataset_name or "", source_table.strip(), source_column.strip(),
                        target_table.strip(), target_column.strip(), status.strip().lower(),
                        cardinality.strip().lower(), created_at
                    ))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to save schema relationship for session {session_id}: {e}")
                return False

    def get_schema_relationships(
        self,
        session_id: str,
        dataset_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves relationship overrides for session_id (and optional dataset_name)."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    if dataset_name:
                        cursor = conn.execute("""
                            SELECT * FROM schema_relationships
                            WHERE session_id = ? AND (dataset_name = ? OR dataset_name = '')
                            ORDER BY id ASC;
                        """, (session_id, dataset_name))
                    else:
                        cursor = conn.execute("""
                            SELECT * FROM schema_relationships
                            WHERE session_id = ?
                            ORDER BY id ASC;
                        """, (session_id,))
                    return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Failed to get schema relationships for session {session_id}: {e}")
                return []

    def delete_schema_relationship(
        self,
        session_id: str,
        dataset_name: str,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str
    ) -> bool:
        """Deletes a relationship override for session_id."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        DELETE FROM schema_relationships
                        WHERE session_id = ? AND (dataset_name = ? OR dataset_name = '')
                          AND source_table = ? AND source_column = ?
                          AND target_table = ? AND target_column = ?;
                    """, (session_id, dataset_name or "", source_table.strip(), source_column.strip(), target_table.strip(), target_column.strip()))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to delete schema relationship for session {session_id}: {e}")
                return False


# Global singleton instance
metadata_manager = MetadataManager()
