"""
backend/routers/history.py - Session Query History Router
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from backend.schemas import HistoryResponse, HistoryEntryItem, GenericMessageResponse
from backend.session_manager import UserSession, get_current_session

router = APIRouter(prefix="/history", tags=["Query History & Session Memory"])


@router.get("", response_model=HistoryResponse, summary="Retrieve Session Query History")
def get_session_history(
    limit: Optional[int] = Query(50, ge=1, le=200, description="Max history entries to return"),
    dataset_name: Optional[str] = Query(None, description="Optional dataset filter"),
    search: Optional[str] = Query(None, description="Search query string"),
    status_filter: Optional[str] = Query(None, description="Status filter: all, success, failed"),
    session: UserSession = Depends(get_current_session)
) -> HistoryResponse:
    """
    Returns the persistent natural-language query logs, SQL statements,
    execution latency, and success states strictly isolated to the caller's session.
    """
    entries = session.query_history.get_recent(
        limit=limit,
        dataset_name=dataset_name,
        search=search,
        status_filter=status_filter
    )
    items = [HistoryEntryItem(**entry.to_dict()) for entry in entries]
    return HistoryResponse(entries=items, count=len(items))


@router.delete("", response_model=GenericMessageResponse, summary="Clear Session Query History")
def clear_session_history(
    dataset_name: Optional[str] = Query(None, description="Optional dataset filter to clear"),
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Clears all execution logs and query history strictly within this user session.
    """
    success = session.query_history.clear_history(dataset_name=dataset_name)
    return GenericMessageResponse(
        success=success,
        message="Session query history successfully cleared." if success else "Failed to clear history."
    )


@router.delete("/{entry_id}", response_model=GenericMessageResponse, summary="Delete Specific Query History Entry")
def delete_history_entry(
    entry_id: int,
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Deletes a single history entry strictly within this user session.
    """
    success = session.query_history.delete_entry(entry_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete history entry {entry_id}."
        )
    return GenericMessageResponse(
        success=True,
        message=f"History entry {entry_id} successfully deleted."
    )
