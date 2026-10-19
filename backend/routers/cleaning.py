"""
backend/routers/cleaning.py - Conversational Data Cleaning & Transformation Router
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
import logging

from backend.schemas import (
    CleaningPreviewResponse,
    CleaningApplyResponse,
    CleaningCancelResponse,
    CleaningUndoResponse,
    CleaningPromptRequest,
    CleaningDirectRequest,
    GenericMessageResponse
)
from backend.session_manager import UserSession, get_current_session
from cleaning_engine import cleaning_engine

logger = logging.getLogger("dataverse.api.cleaning")
router = APIRouter(prefix="/clean", tags=["Conversational Data Cleaning"])


@router.post("/analyze", summary="Analyze Missing Values and Duplicates in Active Dataset")
def analyze_dataset_cleaning(
    table_name: Optional[str] = None,
    session: UserSession = Depends(get_current_session)
) -> Dict[str, Any]:
    """
    Performs comprehensive diagnostic analysis on the session's active dataset:
    - Missing value percentages and smart imputation recommendations per column
    - Exact and subset duplicate row detection with sample duplicate records
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a dataset before analyzing."
        )

    try:
        tbl, df = session.get_active_dataframe(table_name)
        missing_analysis = cleaning_engine.analyze_missing(df)
        dup_analysis = cleaning_engine.analyze_duplicates(df)

        return {
            "table_name": tbl,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "missing": missing_analysis,
            "duplicates": dup_analysis
        }
    except Exception as e:
        logger.error(f"Error analyzing dataset for session {session.session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to analyze dataset: {str(e)}"
        )


@router.post("/preview", response_model=CleaningPreviewResponse, summary="Generate Transformation Preview without Modifying Data")
def generate_cleaning_preview(
    payload: CleaningPromptRequest,
    session: UserSession = Depends(get_current_session)
) -> CleaningPreviewResponse:
    """
    Parses a natural language cleaning request (e.g. 'remove duplicates', 'fill missing age with median')
    or structured request, computes the transformation on a defensive working copy,
    and returns before-and-after samples with affected counts.
    Never modifies the underlying dataset until explicitly applied.
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a dataset first."
        )

    try:
        tbl, df = session.get_active_dataframe(payload.table_name)
        columns = list(df.columns)

        # Parse natural language prompt into structured cleaning plan
        plan = cleaning_engine.parse_cleaning_prompt(payload.prompt, columns=columns, table_name=tbl)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse data cleaning action from prompt: '{payload.prompt}'. "
                       f"Supported actions: handle missing values, remove duplicates, convert column types, "
                       f"filter invalid rows, normalize text."
            )

        # Generate preview
        preview_data = cleaning_engine.generate_preview(df, plan)
        transformed_df = preview_data.pop("transformed_df")

        # Cache pending transformation in session memory for confirmation
        session.set_pending_transformation(preview_data, transformed_df)

        return CleaningPreviewResponse(**preview_data)

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error generating cleaning preview for session {session.session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cleaning preview error: {str(e)}")


@router.post("/direct-preview", response_model=CleaningPreviewResponse, summary="Generate Transformation Preview from Structured Plan")
def generate_direct_cleaning_preview(
    payload: CleaningDirectRequest,
    session: UserSession = Depends(get_current_session)
) -> CleaningPreviewResponse:
    """
    Generates a cleaning preview from a direct structured plan (operation + params).
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a dataset first."
        )

    try:
        tbl, df = session.get_active_dataframe(payload.table_name)
        plan = {
            "operation": payload.operation,
            "table_name": tbl,
            "params": payload.params
        }
        preview_data = cleaning_engine.generate_preview(df, plan)
        transformed_df = preview_data.pop("transformed_df")

        session.set_pending_transformation(preview_data, transformed_df)
        return CleaningPreviewResponse(**preview_data)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in direct cleaning preview for session {session.session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/apply", response_model=CleaningApplyResponse, summary="Apply Approved Transformation to Dataset")
def apply_cleaning_transformation(
    session: UserSession = Depends(get_current_session)
) -> CleaningApplyResponse:
    """
    Applies the pending preview transformation to the active working copy in SQLite.
    Preserves prior state in a revision history stack for undo capability.
    """
    if not session.pending_transformation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending transformation proposal to apply. Please generate a preview first."
        )

    try:
        preview = session.apply_pending_transformation()
        tbl, df = session.get_active_dataframe(preview.get("table_name"))

        # Log to query history as an auditable data transformation event
        session.query_history.add_entry(
            question=f"Data Cleaning: {preview.get('description')}",
            sql_query=f"-- Applied transformation: {preview.get('operation')} ({preview.get('rows_affected')} rows affected)",
            success=True,
            row_count=len(df),
            execution_time=0.01,
            dataset_name=session.active_dataset
        )

        return CleaningApplyResponse(
            success=True,
            message=f"Transformation applied successfully: {preview.get('description')}",
            operation=preview.get("operation"),
            table_name=tbl,
            rows_current=len(df),
            columns_current=len(df.columns),
            columns=list(df.columns),
            revisions_count=len(session.dataset_revisions)
        )
    except Exception as e:
        logger.error(f"Failed to apply transformation for session {session.session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Apply error: {str(e)}")


@router.post("/cancel", response_model=CleaningCancelResponse, summary="Cancel Pending Transformation")
def cancel_cleaning_transformation(
    session: UserSession = Depends(get_current_session)
) -> CleaningCancelResponse:
    """
    Cancels and discards the pending transformation proposal.
    Guarantees no modifications are made to the dataset.
    """
    cancelled = session.cancel_pending_transformation()
    return CleaningCancelResponse(
        success=True,
        message="Transformation proposal cancelled. No changes were made to your dataset." if cancelled else "No pending transformation to cancel."
    )


@router.post("/undo", response_model=CleaningUndoResponse, summary="Undo Last Applied Cleaning Transformation")
def undo_cleaning_transformation(
    session: UserSession = Depends(get_current_session)
) -> CleaningUndoResponse:
    """
    Reverts the last applied cleaning transformation and restores the prior dataset state.
    """
    result = session.undo_last_transformation()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous revisions available to undo."
        )

    return CleaningUndoResponse(
        success=True,
        message=f"Reverted last transformation ({result.get('reverted_description')}).",
        table_name=result.get("table_name"),
        rows_restored=result.get("rows_restored"),
        columns_restored=result.get("columns_restored"),
        revisions_remaining=result.get("revisions_remaining", 0)
    )


@router.post("/revert-original", response_model=GenericMessageResponse, summary="Revert Table to Original Upload Snapshot")
def revert_dataset_to_original(
    table_name: Optional[str] = None,
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Completely restores the active working table to its original immutable snapshot captured upon upload.
    """
    result = session.revert_to_original(table_name)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No original snapshot found for this dataset."
        )

    return GenericMessageResponse(
        success=True,
        message=f"Dataset '{result.get('table_name')}' restored to original uploaded snapshot ({result.get('rows_restored')} rows, {result.get('columns_restored')} columns)."
    )
