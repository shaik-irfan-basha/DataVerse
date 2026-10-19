"""
backend/routers/schema_visualizer.py - Relational Schema Visualizer & Join Query Router
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from backend.schemas import (
    SchemaVisualizerResponse,
    TableVisualizerInfo,
    ColumnVisualizerInfo,
    RelationshipVisualizerInfo,
    RelationshipActionRequest,
    CustomRelationshipRequest,
    RelationshipActionResponse,
    JoinGenerateRequest,
    JoinGenerateResponse,
    GenericMessageResponse
)
from backend.session_manager import UserSession, get_current_session
from schema_engine import schema_engine
from metadata_manager import metadata_manager

logger = logging.getLogger("dataverse.api.schema_visualizer")
router = APIRouter(prefix="/schema", tags=["Relational Schema Visualizer"])


@router.get("/visualize", response_model=SchemaVisualizerResponse, summary="Discover Schema & Relationships for ER Diagram")
def get_schema_visualization(
    session: UserSession = Depends(get_current_session)
) -> SchemaVisualizerResponse:
    """
    Returns full relational schema architecture for the session's active dataset:
    - Tables, columns, data types, null rates, uniqueness, explicit/inferred primary keys.
    - Explicit foreign keys from SQLite DDL.
    - Heuristically inferred relationship candidates with confidence scores and value overlap metrics.
    - User confirmed/rejected overrides persisted for this session and dataset.
    """
    tables_dict = schema_engine.discover_schema(session.data_connector)
    relationships_list = schema_engine.infer_relationships(
        connector=session.data_connector,
        tables=tables_dict,
        session_id=session.session_id,
        dataset_name=session.active_dataset
    )

    table_models: List[TableVisualizerInfo] = []
    for t_name, t_detail in tables_dict.items():
        col_models: List[ColumnVisualizerInfo] = []
        for c in t_detail.columns:
            col_models.append(ColumnVisualizerInfo(
                name=c.name,
                data_type=c.data_type,
                is_pk=c.is_pk,
                is_fk=c.is_fk,
                fk_target_table=c.fk_target_table,
                fk_target_column=c.fk_target_column,
                is_nullable=c.is_nullable,
                total_count=c.total_count,
                null_count=c.null_count,
                null_rate=c.null_rate,
                unique_count=c.unique_count,
                unique_rate=c.unique_rate,
                sample_values=c.sample_values
            ))
        table_models.append(TableVisualizerInfo(
            table_name=t_detail.table_name,
            row_count=t_detail.row_count,
            columns=col_models,
            primary_keys=t_detail.primary_keys
        ))

    rel_models: List[RelationshipVisualizerInfo] = []
    confirmed_count = 0
    inferred_count = 0
    rejected_count = 0

    for r in relationships_list:
        if r.status == "confirmed":
            confirmed_count += 1
        elif r.status == "rejected":
            rejected_count += 1
        else:
            inferred_count += 1

        rel_models.append(RelationshipVisualizerInfo(
            id=r.id,
            source_table=r.source_table,
            source_column=r.source_column,
            target_table=r.target_table,
            target_column=r.target_column,
            cardinality=r.cardinality,
            status=r.status,
            confidence=r.confidence,
            source=r.source,
            overlap_percentage=r.overlap_percentage,
            overlap_count=r.overlap_count,
            sample_matches=r.sample_matches,
            is_ambiguous=r.is_ambiguous,
            ambiguity_note=r.ambiguity_note,
            user_confirmed=r.user_confirmed,
            user_rejected=r.user_rejected
        ))

    return SchemaVisualizerResponse(
        is_loaded=len(table_models) > 0,
        dataset_name=session.active_dataset,
        table_count=len(table_models),
        tables=table_models,
        relationships=rel_models,
        confirmed_count=confirmed_count,
        inferred_count=inferred_count,
        rejected_count=rejected_count
    )


@router.post("/relationships/confirm", response_model=RelationshipActionResponse, summary="Confirm Inferred Relationship")
def confirm_relationship(
    req: RelationshipActionRequest,
    session: UserSession = Depends(get_current_session)
) -> RelationshipActionResponse:
    """
    Promotes an inferred candidate relationship to confirmed status and persists it in SQLite metadata.
    """
    tables = schema_engine.discover_schema(session.data_connector)
    if req.source_table not in tables or req.target_table not in tables:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source or target table does not exist in the active schema."
        )

    saved = metadata_manager.save_schema_relationship(
        session_id=session.session_id,
        dataset_name=session.active_dataset,
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        status="confirmed",
        cardinality=req.cardinality or "one-to-many"
    )

    if not saved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist confirmed relationship."
        )

    rel_id = f"{req.source_table}.{req.source_column}->{req.target_table}.{req.target_column}"
    return RelationshipActionResponse(
        success=True,
        message=f"Relationship '{rel_id}' confirmed successfully.",
        relationship_id=rel_id,
        status="confirmed",
        cardinality=req.cardinality or "one-to-many"
    )


@router.post("/relationships/reject", response_model=RelationshipActionResponse, summary="Reject Inferred Relationship")
def reject_relationship(
    req: RelationshipActionRequest,
    session: UserSession = Depends(get_current_session)
) -> RelationshipActionResponse:
    """
    Rejects an inferred relationship candidate so it is excluded from active consideration.
    """
    saved = metadata_manager.save_schema_relationship(
        session_id=session.session_id,
        dataset_name=session.active_dataset,
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        status="rejected",
        cardinality=req.cardinality or "one-to-many"
    )

    if not saved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist rejected relationship status."
        )

    rel_id = f"{req.source_table}.{req.source_column}->{req.target_table}.{req.target_column}"
    return RelationshipActionResponse(
        success=True,
        message=f"Relationship '{rel_id}' rejected.",
        relationship_id=rel_id,
        status="rejected",
        cardinality=req.cardinality or "one-to-many"
    )


@router.post("/relationships/custom", response_model=RelationshipActionResponse, summary="Create Custom Relationship")
def create_custom_relationship(
    req: CustomRelationshipRequest,
    session: UserSession = Depends(get_current_session)
) -> RelationshipActionResponse:
    """
    Creates a user-defined relationship between two tables and columns with validated identifiers.
    """
    tables = schema_engine.discover_schema(session.data_connector)
    if req.source_table not in tables:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Source table '{req.source_table}' not found.")
    if req.target_table not in tables:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Target table '{req.target_table}' not found.")

    src_cols = [c.name for c in tables[req.source_table].columns]
    tgt_cols = [c.name for c in tables[req.target_table].columns]

    if req.source_column not in src_cols:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Column '{req.source_column}' not found in table '{req.source_table}'.")
    if req.target_column not in tgt_cols:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Column '{req.target_column}' not found in table '{req.target_table}'.")

    saved = metadata_manager.save_schema_relationship(
        session_id=session.session_id,
        dataset_name=session.active_dataset,
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        status="confirmed",
        cardinality=req.cardinality or "one-to-many"
    )

    if not saved:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to persist custom relationship.")

    rel_id = f"{req.source_table}.{req.source_column}->{req.target_table}.{req.target_column}"
    return RelationshipActionResponse(
        success=True,
        message=f"Custom relationship '{rel_id}' created successfully.",
        relationship_id=rel_id,
        status="confirmed",
        cardinality=req.cardinality or "one-to-many"
    )


@router.delete("/relationships", response_model=GenericMessageResponse, summary="Delete Relationship Override")
def delete_relationship_override(
    source_table: str = Query(..., min_length=1),
    source_column: str = Query(..., min_length=1),
    target_table: str = Query(..., min_length=1),
    target_column: str = Query(..., min_length=1),
    session: UserSession = Depends(get_current_session)
) -> GenericMessageResponse:
    """
    Removes a previously saved relationship override or custom relationship.
    """
    deleted = metadata_manager.delete_schema_relationship(
        session_id=session.session_id,
        dataset_name=session.active_dataset,
        source_table=source_table,
        source_column=source_column,
        target_table=target_table,
        target_column=target_column
    )

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship override not found.")

    return GenericMessageResponse(
        success=True,
        message=f"Override for {source_table}.{source_column}->{target_table}.{target_column} removed."
    )


@router.post("/generate-join", response_model=JoinGenerateResponse, summary="Generate Validated SQLite JOIN Query")
def generate_join_query(
    req: JoinGenerateRequest,
    session: UserSession = Depends(get_current_session)
) -> JoinGenerateResponse:
    """
    Generates a validated SQLite JOIN query between two tables.
    Returns SQL, join condition, explanation, and ambiguity notices.
    """
    try:
        tables = schema_engine.discover_schema(session.data_connector)
        relationships = schema_engine.infer_relationships(
            connector=session.data_connector,
            tables=tables,
            session_id=session.session_id,
            dataset_name=session.active_dataset
        )

        res = schema_engine.generate_join_sql(
            connector=session.data_connector,
            table_a=req.table_a,
            table_b=req.table_b,
            join_type=req.join_type or "INNER JOIN",
            source_column=req.source_column,
            target_column=req.target_column,
            relationships=relationships
        )

        avail_rels: List[RelationshipVisualizerInfo] = [
            RelationshipVisualizerInfo(**r) for r in res.get("available_relationships", [])
        ]

        return JoinGenerateResponse(
            sql=res["sql"],
            table_a=res["table_a"],
            table_b=res["table_b"],
            join_type=res["join_type"],
            join_condition=res["join_condition"],
            explanation=res["explanation"],
            is_ambiguous=res["is_ambiguous"],
            available_relationships=avail_rels
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error generating join query: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Join generation error: {str(e)}")
