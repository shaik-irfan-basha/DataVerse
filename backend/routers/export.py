"""
backend/routers/export.py - Query Result File Export Router
"""

import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
import logging

from backend.schemas import ExportRequest
from backend.session_manager import UserSession, get_current_session

logger = logging.getLogger("dataverse.api.export")
router = APIRouter(tags=["Export & Serialization"])

MIME_TYPES = {
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json"
}


@router.post("/export", summary="Export Results to Downloadable CSV, Excel, or JSON File")
def export_results(
    payload: ExportRequest,
    session: UserSession = Depends(get_current_session)
):
    """
    Serializes tabular query results into RFC 4180 CSV, styled Microsoft Excel, or JSON.
    Streams the file back to the browser or mobile client with appropriate download headers.
    """
    if not payload.columns or not payload.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot export empty columns or rows."
        )

    fmt = payload.format.lower().strip()
    if fmt not in ["csv", "excel", "xlsx", "json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{fmt}'. Choose 'csv', 'excel', or 'json'."
        )

    ext = "xlsx" if fmt in ["excel", "xlsx"] else fmt
    default_name = f"dataverse_export_{uuid.uuid4().hex[:8]}.{ext}"
    download_filename = payload.filename or default_name
    if not download_filename.endswith(f".{ext}"):
        download_filename = f"{download_filename}.{ext}"

    target_file = session.temp_dir / f"export_{uuid.uuid4().hex[:8]}.{ext}"
    tuple_rows = [tuple(r) for r in payload.rows]

    try:
        session.query_service.export_results(
            columns=payload.columns,
            rows=tuple_rows,
            file_path=str(target_file),
            format_type=fmt
        )

        if not target_file.exists():
            raise RuntimeError("Export file was not created by the engine.")

        media_type = MIME_TYPES.get(fmt, "application/octet-stream")
        return FileResponse(
            path=str(target_file),
            media_type=media_type,
            filename=download_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error exporting query results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )
