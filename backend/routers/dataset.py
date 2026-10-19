"""
backend/routers/dataset.py - Dataset Ingestion & Schema Inspection Router
"""

import os
from pathlib import Path
from typing import Dict, List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
import logging

from backend.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES
from backend.schemas import (
    FileUploadResponse,
    SchemaResponse,
    SuggestionsResponse,
    ColumnMeta
)
from backend.session_manager import UserSession, get_current_session
from suggested_questions import SuggestedQuestionsGenerator

logger = logging.getLogger("dataverse.api.dataset")
router = APIRouter(tags=["Dataset Ingestion & Schema"])


@router.post("/upload", response_model=FileUploadResponse, summary="Upload & Ingest Dataset into Session Sandbox")
async def upload_dataset(
    file: UploadFile = File(..., description="Dataset file (CSV, Excel, JSON, or SQLite database)"),
    session: UserSession = Depends(get_current_session)
) -> FileUploadResponse:
    """
    Ingests an uploaded data file into the user's isolated in-memory SQLite sandbox.
    Enforces file extension whitelisting, filename sanitization, and size caps.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Sanitize filename to prevent path traversal
    safe_name = Path(file.filename).name
    destination = session.temp_dir / safe_name

    # Stream write with byte-counter guard
    bytes_written = 0
    chunk_size = 1024 * 64  # 64 KB chunks

    try:
        with open(destination, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    # File exceeded max size limit
                    buffer.close()
                    if destination.exists():
                        destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to write uploaded file {safe_name}: {e}")
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process file upload: {str(e)}")

    # Load file into session's private DataConnector
    try:
        tables_created = session.data_connector.load_file(str(destination))
        session.set_active_dataset(safe_name)
        session.record_original_tables(tables_created)
        raw_schema = session.data_connector.get_schema()

        # Format schema for API response
        schema_overview: Dict[str, List[ColumnMeta]] = {}
        for table, cols in raw_schema.items():
            schema_overview[table] = [
                ColumnMeta(column=c["name"], type=c["type"] or "TEXT", nullable=True)
                for c in cols
            ]

        # Generate schema-aware starter questions
        suggestions = SuggestedQuestionsGenerator.generate(session.data_connector, max_questions=5)

        return FileUploadResponse(
            session_id=session.session_id,
            filename=safe_name,
            file_type=session.data_connector.file_type or "Unknown",
            tables_created=tables_created,
            schema_overview=schema_overview,
            suggested_questions=suggestions
        )
    except Exception as e:
        logger.error(f"Error loading file into session {session.session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Data parser error while loading '{safe_name}': {str(e)}"
        )


@router.get("/schema", response_model=SchemaResponse, summary="Inspect Active Tables & Schema")
def get_schema(session: UserSession = Depends(get_current_session)) -> SchemaResponse:
    """
    Returns the schema, column types, and active table names in the session's sandbox.
    """
    is_loaded = session.data_connector.is_loaded()
    if not is_loaded:
        return SchemaResponse(is_loaded=False, tables=[], schema_overview={})

    raw_schema = session.data_connector.get_schema()
    schema_overview: Dict[str, List[ColumnMeta]] = {}
    for table, cols in raw_schema.items():
        schema_overview[table] = [
            ColumnMeta(column=c["name"], type=c["type"] or "TEXT", nullable=True)
            for c in cols
        ]

    return SchemaResponse(
        is_loaded=True,
        tables=list(raw_schema.keys()),
        schema_overview=schema_overview
    )


@router.get("/suggestions", response_model=SuggestionsResponse, summary="Get Schema-Aware Suggested Questions")
def get_suggestions(session: UserSession = Depends(get_current_session)) -> SuggestionsResponse:
    """
    Dynamically generates contextual starter questions based on the session's active schema.
    """
    if not session.data_connector.is_loaded():
        return SuggestionsResponse(suggestions=[])

    suggestions = SuggestedQuestionsGenerator.generate(session.data_connector, max_questions=5)
    return SuggestionsResponse(suggestions=suggestions)
