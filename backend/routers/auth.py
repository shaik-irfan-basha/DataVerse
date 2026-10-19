"""
backend/routers/auth.py - Session Authentication Router
"""

from fastapi import APIRouter
from datetime import datetime, timezone
from backend.config import SESSION_TTL_SECONDS
from backend.schemas import SessionCreateResponse
from backend.session_manager import session_manager

router = APIRouter(prefix="/auth", tags=["Authentication & Sessions"])


@router.post("/session", response_model=SessionCreateResponse, summary="Create Isolated User Session")
def create_session() -> SessionCreateResponse:
    """
    Generates a cryptographically secure session ID and bearer token.
    Allocates an isolated in-memory SQLite database and query history for the client.
    """
    session_id, raw_token = session_manager.create_session()

    return SessionCreateResponse(
        session_id=session_id,
        session_token=raw_token,
        expires_in=SESSION_TTL_SECONDS,
        created_at=datetime.now(timezone.utc).isoformat()
    )
