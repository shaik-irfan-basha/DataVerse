"""
backend/routers/analytics.py - Table Profiling & Auto-Visualization Router
"""

import io
import base64
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
import matplotlib.pyplot as plt

from backend.schemas import ChartRequest, ChartResponse, TableProfileResponse
from backend.session_manager import UserSession, get_current_session
from chart_engine import ChartEngine

router = APIRouter(tags=["Analytics & Profiling"])


@router.get("/profile/{table}", response_model=TableProfileResponse, summary="Generate Statistical Column Profile for Table")
def get_table_profile(
    table: str,
    session: UserSession = Depends(get_current_session)
) -> TableProfileResponse:
    """
    Computes statistical diagnostics (null rates, uniqueness, numeric distributions,
    and categorical rankings) for a specific loaded table in the session.
    """
    if not session.data_connector.is_loaded():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset loaded in this session."
        )

    schema = session.data_connector.get_schema()
    if table not in schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table}' does not exist. Available tables: {list(schema.keys())}"
        )

    try:
        profile = session.query_service.profile_table(table)
        return TableProfileResponse(**profile.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to profile table '{table}': {str(e)}"
        )


@router.post("/chart", response_model=ChartResponse, summary="Auto-Generate Visualizations from Tabular Results")
def generate_chart(
    payload: ChartRequest,
    session: UserSession = Depends(get_current_session)
) -> ChartResponse:
    """
    Analyzes column types and data distributions to generate:
    1. Base64 data-URL for static PNG rendering (Matplotlib dark theme).
    2. Structured JSON categories & series for client-side interactive rendering.
    """
    if not payload.columns or not payload.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Columns and rows must not be empty to generate a chart."
        )

    tuple_rows = [tuple(r) for r in payload.rows]
    chart_type_detected = ChartEngine.detect_chart_type(payload.columns, tuple_rows)
    effective_chart_type = payload.chart_type if payload.chart_type and payload.chart_type != "auto" else chart_type_detected

    if effective_chart_type == "none":
        effective_chart_type = "bar"

    # Generate Matplotlib figure
    fig = None
    try:
        fig = ChartEngine.create_figure(
            columns=payload.columns,
            rows=tuple_rows,
            chart_type=effective_chart_type,
            title=payload.title or ""
        )

        # Save to buffer
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{img_b64}"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chart generation error: {str(e)}"
        )
    finally:
        if fig:
            plt.close(fig)

    # Extract JSON series data for interactive client charts
    labels: List[str] = []
    datasets: List[Dict[str, Any]] = []

    # Simple extraction for client-side charting
    if len(payload.columns) >= 2:
        labels = [str(r[0]) for r in payload.rows[:30]]
        for col_idx in range(1, len(payload.columns)):
            col_name = payload.columns[col_idx]
            values = []
            for r in payload.rows[:30]:
                val = r[col_idx]
                try:
                    values.append(float(val) if val is not None else 0.0)
                except (ValueError, TypeError):
                    values.append(0.0)
            datasets.append({
                "label": col_name,
                "data": values
            })

    return ChartResponse(
        chart_type=effective_chart_type,
        base64_image=data_url,
        series_data={
            "labels": labels,
            "datasets": datasets
        }
    )
