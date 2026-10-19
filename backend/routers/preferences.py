"""
backend/routers/preferences.py - Session-Isolated User Preferences Router
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.schemas import (
    PreferenceSetRequest,
    PreferencesResponse,
    GenericMessageResponse
)
from backend.session_manager import UserSession, get_current_session
from metadata_manager import metadata_manager

router = APIRouter(prefix="/preferences", tags=["User Preferences"])


@router.get("", response_model=PreferencesResponse, summary="Get All User Preferences")
def get_all_preferences(session: UserSession = Depends(get_current_session)) -> PreferencesResponse:
    """
    Returns all non-secret user preferences (theme, view settings, defaults)
    strictly isolated to the caller's session.
    """
    prefs = metadata_manager.get_all_preferences(session.session_id)
    return PreferencesResponse(preferences=prefs)


@router.put("", response_model=GenericMessageResponse, summary="Set / Update User Preference")
def set_preference(
    payload: PreferenceSetRequest,
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Saves or updates a user preference key-value pair.
    Guarantees secret exclusion (API keys are forbidden in preferences).
    """
    try:
        success = metadata_manager.set_preference(
            session_id=session.session_id,
            key=payload.key,
            value=payload.value
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to persist preference.")
        return GenericMessageResponse(success=True, message=f"Preference '{payload.key}' saved successfully.")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get("/{key}", summary="Get Specific User Preference")
def get_preference(
    key: str,
    session: UserSession = Depends(get_current_session)
):
    """
    Retrieves a single preference value by key.
    """
    val = metadata_manager.get_preference(session.session_id, key)
    if val is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preference '{key}' not found."
        )
    return {"key": key, "value": val}


@router.delete("/{key}", response_model=GenericMessageResponse, summary="Delete User Preference")
def delete_preference(
    key: str,
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Removes a user preference key.
    """
    success = metadata_manager.delete_preference(session.session_id, key)
    return GenericMessageResponse(
        success=success,
        message=f"Preference '{key}' deleted." if success else f"Preference '{key}' was not set."
    )
