"""
backend/routers/saved_queries.py - Session-Isolated Saved Queries & Bookmarks Router
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from backend.schemas import (
    SavedQueryCreateRequest,
    SavedQueryItem,
    SavedQueriesResponse,
    GenericMessageResponse
)
from backend.session_manager import UserSession, get_current_session
from metadata_manager import metadata_manager

router = APIRouter(prefix="/saved-queries", tags=["Saved Queries & Bookmarks"])


@router.get("", response_model=SavedQueriesResponse, summary="List Saved Queries & Bookmarks")
def get_saved_queries(
    dataset_name: Optional[str] = Query(None, description="Optional dataset filter"),
    search: Optional[str] = Query(None, description="Optional search term"),
    session: UserSession = Depends(get_current_session)
) -> SavedQueriesResponse:
    """
    Returns bookmarked/saved queries strictly isolated to the caller's session.
    """
    records = metadata_manager.get_saved_queries(
        session_id=session.session_id,
        dataset_name=dataset_name,
        search=search
    )
    items = [SavedQueryItem(**r) for r in records]
    return SavedQueriesResponse(saved_queries=items, count=len(items))


@router.post("", response_model=SavedQueryItem, status_code=status.HTTP_201_CREATED, summary="Bookmark / Save a Query")
def create_saved_query(
    payload: SavedQueryCreateRequest,
    session: UserSession = Depends(get_current_session)
) -> SavedQueryItem:
    """
    Bookmarks a SQL query with title, question, dataset name, and optional notes.
    Guarantees session isolation and secret exclusion.
    """
    try:
        new_id = metadata_manager.save_query(
            session_id=session.session_id,
            title=payload.title,
            sql_query=payload.sql_query,
            question=payload.question or "",
            dataset_name=payload.dataset_name or session.active_dataset or "",
            notes=payload.notes or ""
        )
        if new_id < 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save query.")

        item = metadata_manager.get_saved_query(session.session_id, new_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve saved query.")
        return SavedQueryItem(**item)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get("/{query_id}", response_model=SavedQueryItem, summary="Get Specific Saved Query")
def get_saved_query(
    query_id: int,
    session: UserSession = Depends(get_current_session)
) -> SavedQueryItem:
    """
    Retrieves a single saved query bookmark ensuring it belongs to the caller's session.
    """
    item = metadata_manager.get_saved_query(session.session_id, query_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved query {query_id} not found or does not belong to this session."
        )
    return SavedQueryItem(**item)


@router.delete("/{query_id}", response_model=GenericMessageResponse, summary="Delete Saved Query")
def delete_saved_query(
    query_id: int,
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Deletes a saved query bookmark strictly within the caller's session.
    """
    success = metadata_manager.delete_saved_query(session.session_id, query_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved query {query_id} not found or does not belong to this session."
        )
    return GenericMessageResponse(
        success=True,
        message=f"Saved query {query_id} successfully deleted."
    )
