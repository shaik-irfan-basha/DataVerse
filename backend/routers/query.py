"""
backend/routers/query.py - Natural Language Query & SQL Execution Router
"""

import os
import re
import time
from typing import Optional
import requests
from fastapi import APIRouter, Depends, HTTPException, status
import logging

from backend.config import ALLOW_SERVER_ENV_KEY
from backend.schemas import (
    QueryRequest,
    QueryResponseModel,
    ExecutionData,
    ManualSqlRequest,
    ManualSqlResponse,
    ClarifyRequest
)
from backend.session_manager import UserSession, get_current_session
from cleaning_engine import cleaning_engine

logger = logging.getLogger("dataverse.api.query")
router = APIRouter(tags=["Query & SQL Execution"])


def _check_session_ai_readiness(session: UserSession) -> Optional[str]:
    """
    Checks if the session is authorized and configured to run AI queries.
    Returns an error message string if not ready, or None if ready.
    """
    if session.llm_api_key:
        return None
    # Allow mock/stub clients injected during unit testing
    if session.query_service and session.query_service.llm_client is not None:
        from llm_client import LLMClient
        if not isinstance(session.query_service.llm_client, LLMClient):
            return None
    if ALLOW_SERVER_ENV_KEY:
        if os.getenv("GROQ_API_KEY"):
            return None
        return "Server environment API key is missing. Please configure your Groq API key in Settings."
    return (
        "AI Provider API key required. DataVerse operates in Bring Your Own Key (BYOK) mode. "
        "Please click the Settings (gear icon in the top header) to enter your free Groq API key."
    )


def _format_ai_error(e: Exception) -> str:
    """Safely formats AI errors without leaking keys or raw tracebacks."""
    if isinstance(e, requests.exceptions.HTTPError) and getattr(e, 'response', None) is not None:
        sc = e.response.status_code
        if sc == 401:
            return "Authentication failed: Configured Groq API key is invalid or unauthorized. Please verify your key in Settings."
        if sc == 429:
            return "Groq rate limit or quota exceeded for this API key. Please check your account at console.groq.com."
        if sc == 404:
            return "Selected AI model was not found on Groq. Please choose a valid model in Settings."
        return f"AI provider returned HTTP {sc}. Please check your key and account limits."
    if isinstance(e, requests.exceptions.Timeout):
        return "AI query request timed out after 30 seconds. Please try again."
    if isinstance(e, requests.exceptions.RequestException):
        return "Network error reaching AI provider. Please verify your connection."
    err_str = str(e)
    # Redact any accidental API key formats and dynamic secrets
    try:
        from logger import _DYNAMIC_SECRETS
        for secret in _DYNAMIC_SECRETS:
            if secret:
                err_str = err_str.replace(secret, '***REDACTED***')
    except Exception:
        pass
    err_str = re.sub(r'gsk_[A-Za-z0-9_-]{10,}', '***REDACTED***', err_str)
    return f"AI engine error: {err_str}"


@router.post("/query", response_model=QueryResponseModel, summary="Execute Natural Language Query via AI Pipeline")
def execute_nl_query(
    payload: QueryRequest,
    session: UserSession = Depends(get_current_session)
) -> QueryResponseModel:
    """
    Translates a natural language question into validated, self-healed SQL and executes it.
    Detects semantic ambiguity and prompts for clarification when necessary.
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a CSV, Excel, JSON, or SQLite dataset before querying."
        )

    t0 = time.time()

    # 1. Check for Conversational Data Cleaning Intent first
    try:
        tbl, df = session.get_active_dataframe()
        columns = list(df.columns)
        cleaning_plan = cleaning_engine.parse_cleaning_prompt(payload.question, columns=columns, table_name=tbl)
        if cleaning_plan:
            op = cleaning_plan.get("operation")
            if op == "analyze_missing":
                missing_info = cleaning_engine.analyze_missing(df)
                total_nulls = missing_info["total_null_cells"]
                cols_with_null = [c for c in missing_info["columns"] if c["null_count"] > 0]
                opts = []
                if cols_with_null:
                    for c in cols_with_null[:2]:
                        if c["is_numeric"]:
                            opts.append(f"Fill missing in {c['column']} with median")
                        else:
                            opts.append(f"Fill missing in {c['column']} with mode")
                    opts.append("Drop rows with missing values")
                else:
                    opts = ["No missing values found!"]
                return QueryResponseModel(
                    status="CLARIFICATION_REQUIRED",
                    clarification_question=f"Missing Value Analysis: Found {total_nulls} missing cell(s) across {len(cols_with_null)} column(s). How would you like to handle them?",
                    clarification_options=opts,
                    reasoning=f"Columns with missing data: {', '.join(c['column'] for c in cols_with_null) if cols_with_null else 'none'}.",
                    original_question=payload.question,
                    clarification_history=payload.clarification_history or "",
                    execution_time=round(time.time() - t0, 4)
                )
            elif op == "analyze_duplicates":
                dup_info = cleaning_engine.analyze_duplicates(df)
                dup_count = dup_info["duplicate_count"]
                opts = ["Remove duplicate rows", "Keep duplicates as-is"] if dup_count > 0 else []
                return QueryResponseModel(
                    status="CLARIFICATION_REQUIRED" if dup_count > 0 else "SUCCESS",
                    clarification_question=f"Duplicate Row Analysis: Found {dup_count} duplicate row(s) ({dup_info['duplicate_percentage']}% of dataset). Would you like to remove them?",
                    clarification_options=opts,
                    reasoning=f"Exact duplicate rows detected: {dup_count} duplicate row(s).",
                    original_question=payload.question,
                    clarification_history=payload.clarification_history or "",
                    execution_time=round(time.time() - t0, 4)
                )
            else:
                # Generate preview for the cleaning transformation
                preview_data = cleaning_engine.generate_preview(df, cleaning_plan)
                transformed_df = preview_data.pop("transformed_df")
                session.set_pending_transformation(preview_data, transformed_df)

                return QueryResponseModel(
                    status="CLEANING_PREVIEW",
                    sql="",
                    clarification_question=f"Data Cleaning Proposal: {preview_data.get('description')}. Would you like to apply these changes to your dataset?",
                    clarification_options=["Apply Transformation", "Cancel"],
                    reasoning=preview_data.get("description", ""),
                    original_question=payload.question,
                    clarification_history=payload.clarification_history or "",
                    cleaning_preview=preview_data,
                    execution_time=round(time.time() - t0, 4)
                )
    except Exception as ce:
        logger.warning(f"Note on cleaning intent parsing: {ce}")

    # 2. Enforce BYOK or development key readiness
    readiness_err = _check_session_ai_readiness(session)
    if readiness_err:
        return QueryResponseModel(
            status="ERROR",
            sql="",
            error_message=readiness_err,
            execution_time=0.0
        )

    try:
        response = session.query_service.query(
            question=payload.question,
            clarification_history=payload.clarification_history or ""
        )
        elapsed = round(time.time() - t0, 4)

        if response.status == "SUCCESS":
            exec_data = response.data or {}
            return QueryResponseModel(
                status="SUCCESS",
                sql=response.sql,
                execution_time=exec_data.get("execution_time", elapsed),
                original_question=payload.question,
                clarification_history=payload.clarification_history or "",
                data=ExecutionData(
                    columns=exec_data.get("columns", []),
                    rows=exec_data.get("rows", []),
                    row_count=exec_data.get("row_count", 0),
                    execution_time=exec_data.get("execution_time", elapsed)
                )
            )
        elif response.status == "CLARIFICATION_REQUIRED":
            return QueryResponseModel(
                status="CLARIFICATION_REQUIRED",
                clarification_question=response.clarification_question,
                clarification_options=response.clarification_options,
                reasoning=getattr(response, "reasoning", "") or "",
                error_message="",
                original_question=payload.question,
                clarification_history=payload.clarification_history or ""
            )
        else:
            return QueryResponseModel(
                status="ERROR",
                sql=response.sql,
                error_message=response.error_message or "Query execution failed.",
                execution_time=elapsed
            )
    except Exception as e:
        logger.error(f"Error executing query for session {session.session_id}: {type(e).__name__}")
        return QueryResponseModel(
            status="ERROR",
            sql="",
            error_message=_format_ai_error(e),
            execution_time=round(time.time() - t0, 4)
        )


@router.post("/sql/execute", response_model=ManualSqlResponse, summary="Execute Manual SQL through Security Validator")
def execute_manual_sql(
    payload: ManualSqlRequest,
    session: UserSession = Depends(get_current_session)
) -> ManualSqlResponse:
    """
    Executes raw SQL directly after verifying it passes SQLValidator and SQLite C-authorizer rules.
    Guarantees no non-read-only queries (DROP, DELETE, UPDATE, INSERT, ALTER) can execute.
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a dataset before executing SQL."
        )

    # Protect against silent execution against the wrong dataset
    active_ds = session.active_dataset or session.query_service._get_active_dataset_name()
    if payload.dataset_name and active_ds and payload.dataset_name.strip() and payload.dataset_name.lower().strip() != active_ds.lower().strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset mismatch: active dataset is '{active_ds}', but this query was recorded for '{payload.dataset_name}'. Please load '{payload.dataset_name}' before rerunning."
        )

    result = session.query_service.execute_manual_sql(payload.sql, question=payload.question)

    if result.get("success"):
        return ManualSqlResponse(
            success=True,
            columns=result.get("columns", []),
            rows=result.get("rows", []),
            row_count=result.get("row_count", 0),
            execution_time=result.get("execution_time", 0.0),
            error=None
        )
    else:
        return ManualSqlResponse(
            success=False,
            columns=[],
            rows=[],
            row_count=0,
            execution_time=result.get("execution_time", 0.0),
            error=result.get("error", "SQL execution failed.")
        )


@router.post("/clarify", response_model=QueryResponseModel, summary="Resume Query Pipeline with User Clarification")
def submit_clarification(
    payload: ClarifyRequest,
    session: UserSession = Depends(get_current_session)
) -> QueryResponseModel:
    """
    Appends the user's clarification answer to the dialogue context and resumes SQL generation.
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded. Please upload a dataset first."
        )

    t0 = time.time()
    clean_resp = payload.user_response.lower().strip()

    # 1. Handle Pending Cleaning Transformation confirmation (Apply / Cancel)
    if session.pending_transformation:
        if clean_resp in ("apply", "apply transformation", "yes", "confirm", "proceed", "accept"):
            try:
                applied = session.apply_pending_transformation()
                tbl, df = session.get_active_dataframe(applied.get("table_name"))

                # Log to session query history
                session.query_history.add_entry(
                    question=f"Data Cleaning: {applied.get('description')}",
                    sql_query=f"-- Applied transformation: {applied.get('operation')} ({applied.get('rows_affected')} rows affected)",
                    success=True,
                    row_count=len(df),
                    execution_time=round(time.time() - t0, 4),
                    dataset_name=session.active_dataset
                )
                return QueryResponseModel(
                    status="SUCCESS",
                    sql=f"-- Transformation Applied: {applied.get('description')}",
                    clarification_question=f"Transformation applied successfully: {applied.get('description')}. Dataset now has {len(df)} rows and {len(df.columns)} columns. You can undo this change at any time.",
                    original_question=payload.original_question,
                    clarification_history=f"{payload.prior_history or ''}\nUser: Apply Transformation\nAI: Applied {applied.get('description')}",
                    execution_time=round(time.time() - t0, 4)
                )
            except Exception as e:
                return QueryResponseModel(
                    status="ERROR",
                    error_message=f"Failed to apply transformation: {str(e)}",
                    execution_time=round(time.time() - t0, 4)
                )
        elif clean_resp in ("cancel", "abort", "no", "discard"):
            session.cancel_pending_transformation()
            return QueryResponseModel(
                status="SUCCESS",
                sql="-- Transformation Cancelled",
                clarification_question="Transformation proposal cancelled. No changes were made to your dataset.",
                original_question=payload.original_question,
                clarification_history=f"{payload.prior_history or ''}\nUser: Cancel\nAI: Transformation proposal cancelled.",
                execution_time=round(time.time() - t0, 4)
            )

    # 2. Check if user clarification is itself a cleaning choice (e.g. "Fill missing in age with median", "Remove duplicate rows")
    try:
        tbl, df = session.get_active_dataframe()
        columns = list(df.columns)
        cleaning_plan = cleaning_engine.parse_cleaning_prompt(payload.user_response, columns=columns, table_name=tbl)
        if cleaning_plan and cleaning_plan.get("operation") not in ("analyze_missing", "analyze_duplicates"):
            preview_data = cleaning_engine.generate_preview(df, cleaning_plan)
            transformed_df = preview_data.pop("transformed_df")
            session.set_pending_transformation(preview_data, transformed_df)
            return QueryResponseModel(
                status="CLEANING_PREVIEW",
                sql="",
                clarification_question=f"Data Cleaning Proposal: {preview_data.get('description')}. Would you like to apply these changes to your dataset?",
                clarification_options=["Apply Transformation", "Cancel"],
                reasoning=preview_data.get("description", ""),
                original_question=payload.original_question,
                clarification_history=payload.prior_history or "",
                cleaning_preview=preview_data,
                execution_time=round(time.time() - t0, 4)
            )
    except Exception as ce:
        logger.warning(f"Clarification cleaning parse note: {ce}")

    # 3. Enforce BYOK or development key readiness for normal NL-to-SQL
    readiness_err = _check_session_ai_readiness(session)
    if readiness_err:
        return QueryResponseModel(
            status="ERROR",
            sql="",
            error_message=readiness_err,
            execution_time=0.0
        )

    prior = (payload.prior_history.strip() + "\n\n") if payload.prior_history else ""
    updated_context = f"{prior}AI: {payload.clarification_question}\nUser: {payload.user_response}\n\n"

    try:
        response = session.query_service.query(
            question=payload.original_question,
            clarification_history=updated_context
        )
        elapsed = round(time.time() - t0, 4)

        if response.status == "SUCCESS":
            exec_data = response.data or {}
            return QueryResponseModel(
                status="SUCCESS",
                sql=response.sql,
                execution_time=exec_data.get("execution_time", elapsed),
                original_question=payload.original_question,
                clarification_history=updated_context,
                data=ExecutionData(
                    columns=exec_data.get("columns", []),
                    rows=exec_data.get("rows", []),
                    row_count=exec_data.get("row_count", 0),
                    execution_time=exec_data.get("execution_time", elapsed)
                )
            )
        elif response.status == "CLARIFICATION_REQUIRED":
            return QueryResponseModel(
                status="CLARIFICATION_REQUIRED",
                clarification_question=response.clarification_question,
                clarification_options=response.clarification_options,
                reasoning=getattr(response, "reasoning", "") or "",
                error_message="",
                original_question=payload.original_question,
                clarification_history=updated_context
            )
        else:
            return QueryResponseModel(
                status="ERROR",
                sql=response.sql,
                error_message=response.error_message or "Clarification recovery failed.",
                execution_time=elapsed
            )
    except Exception as e:
        logger.error(f"Error resuming clarification query: {type(e).__name__}")
        return QueryResponseModel(
            status="ERROR",
            sql="",
            error_message=_format_ai_error(e),
            execution_time=round(time.time() - t0, 4)
        )
