"""
backend/session_manager.py - Cryptographic Multi-Tenant Session Isolation
"""

import os
import shutil
import time
import secrets
import hashlib
import uuid
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any
import logging
import pandas as pd

from fastapi import HTTPException, Request, Header, Depends

from backend.config import SESSION_TTL_SECONDS, TEMP_SESSION_DIR, SUPPORTED_AI_PROVIDERS
from data_connector import DataConnector
from query_history import QueryHistory
from query_service import QueryService
from llm_client import LLMClient
from logger import register_secret_to_scrub
from metadata_manager import metadata_manager

logger = logging.getLogger("dataverse.session_manager")


class UserSession:
    """
    Encapsulates all session-isolated resources for a single client.
    Guarantees strict isolation of datasets, SQLite memory databases, and query histories.
    """
    def __init__(self, session_id: str, token_hash: str):
        self.session_id: str = session_id
        self.token_hash: str = token_hash
        self.created_at: float = time.time()
        self.last_accessed: float = time.time()
        self.active_dataset: str = ""

        # Dedicated disk scratch directory for this session's uploaded/exported files
        self.temp_dir: Path = TEMP_SESSION_DIR / session_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Isolated DataConnector (creates its own private in-memory SQLite database)
        self.data_connector: DataConnector = DataConnector()

        # Isolated QueryHistory (backed by MetadataManager tied strictly to this session_id)
        self.query_history: QueryHistory = QueryHistory(session_id=session_id)

        # Isolated QueryService tied strictly to this session's connector & history
        self.query_service: QueryService = QueryService(
            connector=self.data_connector,
            history=self.query_history
        )

        # Clarification memory for multi-turn sessions
        self.clarification_history: str = ""

        # Phase 3: Conversational Data Cleaning & Reversible Revision Management
        self.original_snapshots: Dict[str, pd.DataFrame] = {}
        self.dataset_revisions: List[Dict[str, Any]] = []
        self.pending_transformation: Optional[Dict[str, Any]] = None

        # AI Provider BYOK configuration (isolated in-memory for this session only)
        self.llm_provider: Optional[str] = None
        self.llm_model: Optional[str] = None
        self.llm_api_key: Optional[str] = None
        self.is_custom_key: bool = False

    def set_provider_config(self, provider: str, model: str, api_key: str):
        """
        Configures the session's isolated AI provider and API key in-memory.
        Immediately attaches an isolated LLMClient to query_service.
        """
        provider = (provider or "groq").lower().strip()
        if provider not in SUPPORTED_AI_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")

        prov_info = SUPPORTED_AI_PROVIDERS[provider]
        valid_model_ids = [m["id"] for m in prov_info.get("models", [])]
        model = (model or prov_info.get("default_model")).strip()
        if model not in valid_model_ids:
            raise ValueError(f"Unsupported model '{model}' for provider '{provider}'")

        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("API key cannot be empty")

        self.llm_provider = provider
        self.llm_model = model
        self.llm_api_key = api_key
        self.is_custom_key = True
        register_secret_to_scrub(api_key)

        # Attach isolated LLMClient to query_service
        self.query_service.llm_client = LLMClient(
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.llm_api_key
        )
        logger.info(f"Configured custom AI provider ({provider}/{model}) for session {self.session_id}")

    def clear_provider_config(self):
        """Removes the session's API key and provider configuration."""
        self.llm_provider = None
        self.llm_model = None
        self.llm_api_key = None
        self.is_custom_key = False
        self.query_service.llm_client = None
        logger.info(f"Cleared AI provider configuration for session {self.session_id}")

    def get_masked_key(self) -> Optional[str]:
        """Returns a safe masked version of the session's API key for display."""
        if not self.llm_api_key:
            return None
        k = self.llm_api_key
        if len(k) <= 8:
            return "••••••••"
        return f"{k[:4]}••••••••{k[-4:]}"

    def touch(self):
        """Refreshes the last-accessed timestamp."""
        self.last_accessed = time.time()

    def set_active_dataset(self, name: str):
        """Sets the active dataset for this session and persists it."""
        self.active_dataset = name or ""
        metadata_manager.update_session_dataset(self.session_id, self.active_dataset)

    # =========================================================================
    # Phase 3: Conversational Data Cleaning & Revision Management Methods
    # =========================================================================

    def record_original_tables(self, tables: List[str]):
        """Records initial immutable snapshots of uploaded tables for reversibility."""
        with self.data_connector._lock:
            conn = self.data_connector.get_connection()
            for t in tables:
                safe_table = self.data_connector._quote_identifier(t)
                try:
                    df = pd.read_sql(f"SELECT * FROM {safe_table}", conn)
                    self.original_snapshots[t] = df.copy()
                except Exception as e:
                    logger.warning(f"Failed to record original snapshot for table {t}: {e}")
        self.dataset_revisions.clear()
        self.pending_transformation = None

    def get_active_dataframe(self, table_name: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Retrieves the active working DataFrame for the specified or primary table."""
        with self.data_connector._lock:
            conn = self.data_connector.get_connection()
            if table_name:
                target_table = table_name
            else:
                schema = self.data_connector.get_schema()
                if not schema:
                    raise ValueError("No table found in active dataset. Please upload a dataset first.")
                target_table = list(schema.keys())[0]

            safe_table = self.data_connector._quote_identifier(target_table)
            df = pd.read_sql(f"SELECT * FROM {safe_table}", conn)
            return target_table, df

    def set_pending_transformation(self, preview_dict: Dict[str, Any], transformed_df: pd.DataFrame):
        """Stores a generated cleaning preview and transformed DataFrame waiting for user confirmation."""
        self.pending_transformation = {
            "preview": preview_dict,
            "transformed_df": transformed_df,
            "created_at": time.time()
        }

    def apply_pending_transformation(self) -> Dict[str, Any]:
        """Applies the pending transformation to the active working table, saving prior state for undo."""
        if not self.pending_transformation:
            raise ValueError("No pending transformation found to apply.")

        preview = self.pending_transformation["preview"]
        transformed_df = self.pending_transformation["transformed_df"]
        table_name = preview.get("table_name") or list(self.data_connector.get_schema().keys())[0]

        with self.data_connector._lock:
            conn = self.data_connector.get_connection()
            # Capture current state for undo
            safe_table = self.data_connector._quote_identifier(table_name)
            current_df = pd.read_sql(f"SELECT * FROM {safe_table}", conn)
            self.dataset_revisions.append({
                "table_name": table_name,
                "df": current_df.copy(),
                "description": preview.get("description", "Data cleaning transformation"),
                "applied_at": time.time()
            })

            # Replace table with cleaned DataFrame
            transformed_df.to_sql(table_name, conn, index=False, if_exists="replace")

        self.pending_transformation = None
        logger.info(f"Applied cleaning transformation on table '{table_name}' for session {self.session_id}")
        return preview

    def cancel_pending_transformation(self) -> bool:
        """Cancels and discards the pending transformation proposal without touching data."""
        had_pending = self.pending_transformation is not None
        self.pending_transformation = None
        return had_pending

    def undo_last_transformation(self) -> Optional[Dict[str, Any]]:
        """Reverts the last applied cleaning transformation to restore the prior state."""
        if not self.dataset_revisions:
            return None

        last_revision = self.dataset_revisions.pop()
        table_name = last_revision["table_name"]
        prior_df = last_revision["df"]

        with self.data_connector._lock:
            conn = self.data_connector.get_connection()
            prior_df.to_sql(table_name, conn, index=False, if_exists="replace")

        logger.info(f"Reverted cleaning transformation on table '{table_name}' for session {self.session_id}")
        return {
            "table_name": table_name,
            "reverted_description": last_revision.get("description", ""),
            "rows_restored": len(prior_df),
            "columns_restored": len(prior_df.columns),
            "revisions_remaining": len(self.dataset_revisions)
        }

    def revert_to_original(self, table_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Reverts table completely to the original uploaded immutable snapshot."""
        if not self.original_snapshots:
            return None

        target_table = table_name or list(self.original_snapshots.keys())[0]
        if target_table not in self.original_snapshots:
            raise ValueError(f"No original snapshot found for table '{target_table}'.")

        orig_df = self.original_snapshots[target_table]
        with self.data_connector._lock:
            conn = self.data_connector.get_connection()
            orig_df.to_sql(target_table, conn, index=False, if_exists="replace")

        self.dataset_revisions.clear()
        self.pending_transformation = None
        logger.info(f"Reverted table '{target_table}' to original uploaded snapshot for session {self.session_id}")
        return {
            "table_name": target_table,
            "rows_restored": len(orig_df),
            "columns_restored": len(orig_df.columns)
        }

    def is_expired(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> bool:
        """Checks if session has exceeded the inactivity TTL."""
        return (time.time() - self.last_accessed) > ttl_seconds

    def cleanup(self):
        """Safely tears down the session's SQLite connections and disk files."""
        try:
            if hasattr(self.data_connector, "connection") and self.data_connector.connection:
                self.data_connector.connection.close()
        except Exception as e:
            logger.warning(f"Error closing session connector for {self.session_id}: {e}")

        # Dereference objects and run garbage collection to release Windows SQLite file locks
        self.llm_api_key = None
        self.llm_model = None
        self.llm_provider = None
        self.query_service = None
        self.query_history = None
        self.data_connector = None
        import gc
        gc.collect()

        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Error removing session directory {self.temp_dir}: {e}")


class SessionManager:
    """
    Thread-safe registry managing cryptographically authenticated sessions.
    Validates token ownership, persists session metadata to dataverse_meta.db,
    rehydrates sessions across server restarts, and enforces automatic TTL eviction.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: Dict[str, UserSession] = {}
        self._token_hash_to_session_id: Dict[str, str] = {}

        # Ensure base temp directory exists
        TEMP_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hashes bearer token with SHA-256 to prevent storing raw tokens in memory."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self) -> Tuple[str, str]:
        """
        Creates a new isolated session and returns (session_id, session_token).
        Uses secrets.token_urlsafe(32) for cryptographic entropy.
        Persists session metadata (NO SECRETS) to dataverse_meta.db.
        """
        with self._lock:
            session_id = f"sess_{uuid.uuid4().hex[:16]}"
            raw_token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(raw_token)

            session = UserSession(session_id=session_id, token_hash=token_hash)
            self._sessions[session_id] = session
            self._token_hash_to_session_id[token_hash] = session_id

            # Persist session metadata into dataverse_meta.db
            metadata_manager.upsert_session(
                session_id=session_id,
                token_hash=token_hash,
                created_at=session.created_at,
                last_accessed=session.last_accessed,
                dataset_name=""
            )

            logger.info(f"Created new isolated session: {session_id}")
            return session_id, raw_token

    def get_session_by_token(self, token: str) -> Optional[UserSession]:
        """
        Validates token, checks expiry, touches session, and returns UserSession.
        If session is not in memory (e.g. after server restart), rehydrates from
        persistent metadata store if within valid TTL.
        Returns None if invalid or expired.
        """
        if not token:
            return None

        token_hash = self._hash_token(token)
        with self._lock:
            session_id = self._token_hash_to_session_id.get(token_hash)
            session = self._sessions.get(session_id) if session_id else None

            # Attempt rehydration if not found in memory (survives server restart)
            if not session:
                persisted = metadata_manager.get_session_by_token_hash(token_hash)
                if persisted:
                    age = time.time() - persisted["last_accessed"]
                    if age <= SESSION_TTL_SECONDS:
                        rehydrated_id = persisted["session_id"]
                        session = UserSession(session_id=rehydrated_id, token_hash=token_hash)
                        session.created_at = persisted["created_at"]
                        session.last_accessed = time.time()
                        session.active_dataset = persisted.get("dataset_name") or ""
                        self._sessions[rehydrated_id] = session
                        self._token_hash_to_session_id[token_hash] = rehydrated_id
                        metadata_manager.touch_session(rehydrated_id, session.last_accessed)
                        logger.info(f"Rehydrated session {rehydrated_id} from persistent metadata store.")
                    else:
                        logger.info(f"Persisted session {persisted['session_id']} has expired. Evicting.")
                        metadata_manager.delete_session(persisted["session_id"])
                        return None
                else:
                    return None

            if session.is_expired():
                logger.info(f"Session {session.session_id} expired. Purging.")
                self.destroy_session(session.session_id, delete_persisted=True)
                return None

            session.touch()
            metadata_manager.touch_session(session.session_id, session.last_accessed)
            return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Internal lookup by session_id without touch."""
        with self._lock:
            return self._sessions.get(session_id)

    def destroy_session(self, session_id: str, delete_persisted: bool = True) -> bool:
        """Explicitly terminates a session and cleans up resources."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                self._token_hash_to_session_id.pop(session.token_hash, None)
                session.cleanup()
                if delete_persisted:
                    metadata_manager.delete_session(session_id)
                logger.info(f"Destroyed session: {session_id} (delete_persisted={delete_persisted})")
                return True
            elif delete_persisted:
                metadata_manager.delete_session(session_id)
            return False

    def cleanup_expired_sessions(self) -> int:
        """Scans and evicts all expired sessions from memory and metadata database."""
        with self._lock:
            expired_ids = [
                sid for sid, sess in self._sessions.items()
                if sess.is_expired()
            ]
            for sid in expired_ids:
                self.destroy_session(sid, delete_persisted=True)
            db_evicted = metadata_manager.cleanup_expired_sessions(SESSION_TTL_SECONDS)
            return len(expired_ids) + db_evicted

    def active_session_count(self) -> int:
        """Returns the number of currently active sessions in memory."""
        with self._lock:
            return len(self._sessions)

    def purge_all(self, delete_persisted: bool = False):
        """Tears down in-memory sessions (preserves persistent metadata by default on server shutdown)."""
        with self._lock:
            sids = list(self._sessions.keys())
            for sid in sids:
                self.destroy_session(sid, delete_persisted=delete_persisted)


# Global Singleton Session Manager
session_manager = SessionManager()


# =============================================================================
# FastAPI Dependency Injection Guard
# =============================================================================

def get_current_session(
    authorization: Optional[str] = Header(None, description="Bearer <session_token>"),
    x_session_token: Optional[str] = Header(None, description="Alternative session token header")
) -> UserSession:
    """
    FastAPI dependency that extracts and validates the cryptographic session token.
    Rejects requests without valid tokens with HTTP 401 Unauthorized.
    """
    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]

    if not token and x_session_token:
        token = x_session_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide 'Authorization: Bearer <token>' or 'X-Session-Token' header."
        )

    session = session_manager.get_session_by_token(token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token. Please create a new session."
        )

    return session
