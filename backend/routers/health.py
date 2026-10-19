"""
backend/routers/health.py - Health and System Status Router
"""

from fastapi import APIRouter
from datetime import datetime, timezone
import config
from backend.schemas import HealthResponse
from backend.session_manager import session_manager

router = APIRouter(tags=["Health & System"])


@router.get("/health", response_model=HealthResponse, summary="System Health & Diagnostic Status")
def get_health() -> HealthResponse:
    """
    Returns the real-time health status, active session counts, and LLM configuration.
    """
    return HealthResponse(
        status="healthy",
        service="dataverse-api",
        version="1.0.0",
        active_sessions=session_manager.active_session_count(),
        llm_provider=getattr(config, "LLM_PROVIDER", "groq"),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
