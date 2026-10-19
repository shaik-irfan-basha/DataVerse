"""
backend/schemas.py - Pydantic Request and Response Contracts
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


# =============================================================================
# Auth & Session Contracts
# =============================================================================

class SessionCreateResponse(BaseModel):
    session_id: str = Field(..., description="Unique public session identifier")
    session_token: str = Field(..., description="Cryptographic bearer authentication token")
    expires_in: int = Field(..., description="Token validity duration in seconds")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


# =============================================================================
# Health Contracts
# =============================================================================

class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Service health status")
    service: str = Field("dataverse-api", description="Service name")
    version: str = Field("1.0.0", description="API version")
    active_sessions: int = Field(..., description="Currently active user sessions")
    llm_provider: str = Field(..., description="Configured LLM provider")
    timestamp: str = Field(..., description="Current server UTC timestamp")


# =============================================================================
# Dataset & Ingestion Contracts
# =============================================================================

class ColumnMeta(BaseModel):
    column: str
    type: str
    nullable: bool = True


class FileUploadResponse(BaseModel):
    session_id: str
    filename: str
    file_type: str
    tables_created: List[str]
    schema_overview: Dict[str, List[ColumnMeta]]
    suggested_questions: List[str] = Field(default_factory=list)


class SchemaResponse(BaseModel):
    is_loaded: bool
    tables: List[str]
    schema_overview: Dict[str, List[ColumnMeta]]


class SuggestionsResponse(BaseModel):
    suggestions: List[str]


# =============================================================================
# Natural Language Query & SQL Execution Contracts
# =============================================================================

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural language question to analyze")
    clarification_history: Optional[str] = Field("", description="Prior clarification conversation history if resuming")


class ExecutionData(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0


class QueryResponseModel(BaseModel):
    status: str = Field(..., description="SUCCESS, CLARIFICATION_REQUIRED, or ERROR")
    sql: str = Field("", description="Generated or recovered SQLite query")
    data: Optional[ExecutionData] = None
    clarification_question: str = ""
    clarification_options: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = Field("", description="Ambiguity explanation or rationale")
    error_message: str = ""
    execution_time: float = 0.0
    original_question: Optional[str] = Field("", description="The original natural language question")
    clarification_history: Optional[str] = Field("", description="Cumulative clarification dialogue history")
    cleaning_preview: Optional[Any] = Field(None, description="Data cleaning transformation proposal if cleaning intent detected")


class ManualSqlRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=5000, description="Raw SQL query string to validate and execute")
    question: Optional[str] = Field("", description="Optional natural language prompt or context for this query")
    dataset_name: Optional[str] = Field(None, description="Optional target dataset name to prevent executing on wrong dataset")


class ManualSqlResponse(BaseModel):
    success: bool
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None


class ClarifyRequest(BaseModel):
    original_question: str = Field(..., min_length=1, max_length=2000)
    clarification_question: str = Field(..., min_length=1)
    user_response: str = Field(..., min_length=1, description="Selected option or custom user clarification text")
    prior_history: Optional[str] = Field("", description="Existing clarification context string")


# =============================================================================
# Data Profiler Contracts
# =============================================================================

class ColumnProfile(BaseModel):
    name: str
    data_type: str
    total_count: int = 0
    null_count: int = 0
    null_percentage: float = 0.0
    unique_count: int = 0
    unique_percentage: float = 0.0
    is_numeric: bool = False
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    median_val: Optional[float] = None
    std_val: Optional[float] = None
    top_values: List[Dict[str, Any]] = Field(default_factory=list)
    sample_values: List[Any] = Field(default_factory=list)


class TableProfileResponse(BaseModel):
    table_name: str
    total_rows: int
    total_columns: int
    columns: List[ColumnProfile] = Field(default_factory=list)


# =============================================================================
# History Contracts
# =============================================================================

class HistoryEntryItem(BaseModel):
    id: Optional[int]
    timestamp: str
    dataset_name: str
    question: str
    sql_query: str
    success: bool
    row_count: int
    execution_time: float
    error_message: str = ""


class HistoryResponse(BaseModel):
    entries: List[HistoryEntryItem]
    count: int


# =============================================================================
# Saved Queries (Bookmarks) Contracts
# =============================================================================

class SavedQueryCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Bookmark title")
    sql_query: str = Field(..., min_length=1, max_length=10000, description="SQL query string")
    question: Optional[str] = Field("", max_length=2000, description="Original natural-language question")
    dataset_name: Optional[str] = Field("", max_length=200, description="Associated dataset name")
    notes: Optional[str] = Field("", max_length=2000, description="User notes or documentation")


class SavedQueryItem(BaseModel):
    id: int
    session_id: str
    title: str
    question: str = ""
    sql_query: str
    dataset_name: str = ""
    created_at: str
    notes: str = ""


class SavedQueriesResponse(BaseModel):
    saved_queries: List[SavedQueryItem]
    count: int


# =============================================================================
# User Preferences Contracts
# =============================================================================

class PreferenceSetRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="Preference key (e.g. theme, default_view, model)")
    value: str = Field(..., max_length=1000, description="Preference value")


class PreferencesResponse(BaseModel):
    preferences: Dict[str, str]


# =============================================================================
# Chart & Export Contracts
# =============================================================================

class ChartRequest(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    chart_type: Optional[str] = "auto"
    title: Optional[str] = ""


class ChartResponse(BaseModel):
    chart_type: str
    base64_image: str = Field(..., description="Base64 data URL for static PNG rendering")
    series_data: Dict[str, Any] = Field(default_factory=dict, description="Structured categories and series for interactive charts")


class ExportRequest(BaseModel):
    format: str = Field("csv", description="Target format: csv, excel, or json")
    columns: List[str]
    rows: List[List[Any]]
    filename: Optional[str] = None


class GenericMessageResponse(BaseModel):
    success: bool
    message: str


# =============================================================================
# Settings & BYOK Contracts
# =============================================================================

class ModelOption(BaseModel):
    id: str
    name: str


class ProviderOption(BaseModel):
    id: str
    name: str
    default_model: str
    models: List[ModelOption]
    key_prefix: Optional[str] = None
    docs_url: Optional[str] = None


class ProviderConfigResponse(BaseModel):
    provider: str
    model: str
    has_key: bool
    masked_key: Optional[str] = None
    allow_server_env_key: bool
    server_key_available: bool
    supported_providers: List[ProviderOption]


class ProviderSaveRequest(BaseModel):
    provider: str = Field("groq", min_length=2, max_length=50)
    model: str = Field("openai/gpt-oss-20b", min_length=2, max_length=100)
    api_key: Optional[str] = Field(None, max_length=256)
    validate_connection: bool = Field(False, description="Verify model and credentials against provider before applying")


class ProviderSaveResponse(BaseModel):
    status: str
    message: str
    provider: str
    model: str
    has_key: bool
    masked_key: Optional[str] = None


class ProviderTestRequest(BaseModel):
    provider: Optional[str] = "groq"
    model: Optional[str] = "openai/gpt-oss-20b"
    api_key: Optional[str] = None


class ProviderTestResponse(BaseModel):
    success: bool
    message: str


# =============================================================================
# Conversational Data Cleaning Contracts
# =============================================================================

class CleaningPreviewResponse(BaseModel):
    operation: str
    table_name: str
    description: str
    rows_before: int
    rows_after: int
    rows_affected: int
    columns_before: List[str]
    columns_after: List[str]
    columns_affected: List[str] = Field(default_factory=list)
    cells_modified: int
    is_destructive: bool
    warning: Optional[str] = ""
    before_sample: List[Dict[str, Any]] = Field(default_factory=list)
    after_sample: List[Dict[str, Any]] = Field(default_factory=list)


class CleaningApplyResponse(BaseModel):
    success: bool
    message: str
    operation: str
    table_name: str
    rows_current: int
    columns_current: int
    columns: List[str] = Field(default_factory=list)
    revisions_count: int = 0


class CleaningCancelResponse(BaseModel):
    success: bool
    message: str


class CleaningUndoResponse(BaseModel):
    success: bool
    message: str
    table_name: str
    rows_restored: int
    columns_restored: int
    revisions_remaining: int


class CleaningPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language data cleaning request")
    table_name: Optional[str] = None


class CleaningDirectRequest(BaseModel):
    operation: str = Field(..., description="handle_missing, remove_duplicates, convert_type, filter_rows, normalize_text")
    table_name: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class CleaningAnalysisRequest(BaseModel):
    table_name: Optional[str] = None


# =============================================================================
# Relational Schema Visualizer Contracts (Phase 4)
# =============================================================================

class ColumnVisualizerInfo(BaseModel):
    name: str
    data_type: str
    is_pk: bool = False
    is_fk: bool = False
    fk_target_table: Optional[str] = None
    fk_target_column: Optional[str] = None
    is_nullable: bool = True
    total_count: int = 0
    null_count: int = 0
    null_rate: float = 0.0
    unique_count: int = 0
    unique_rate: float = 0.0
    sample_values: List[Any] = Field(default_factory=list)


class TableVisualizerInfo(BaseModel):
    table_name: str
    row_count: int
    columns: List[ColumnVisualizerInfo] = Field(default_factory=list)
    primary_keys: List[str] = Field(default_factory=list)


class RelationshipVisualizerInfo(BaseModel):
    id: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    cardinality: str  # 'one-to-one', 'one-to-many', 'many-to-many'
    status: str  # 'confirmed', 'inferred', 'rejected'
    confidence: float
    source: str  # 'explicit_fk', 'inferred', 'user_custom'
    overlap_percentage: float = 0.0
    overlap_count: int = 0
    sample_matches: List[Any] = Field(default_factory=list)
    is_ambiguous: bool = False
    ambiguity_note: Optional[str] = None
    user_confirmed: bool = False
    user_rejected: bool = False


class SchemaVisualizerResponse(BaseModel):
    is_loaded: bool
    dataset_name: str = ""
    table_count: int = 0
    tables: List[TableVisualizerInfo] = Field(default_factory=list)
    relationships: List[RelationshipVisualizerInfo] = Field(default_factory=list)
    confirmed_count: int = 0
    inferred_count: int = 0
    rejected_count: int = 0


class RelationshipActionRequest(BaseModel):
    source_table: str = Field(..., min_length=1)
    source_column: str = Field(..., min_length=1)
    target_table: str = Field(..., min_length=1)
    target_column: str = Field(..., min_length=1)
    cardinality: Optional[str] = "one-to-many"


class CustomRelationshipRequest(BaseModel):
    source_table: str = Field(..., min_length=1)
    source_column: str = Field(..., min_length=1)
    target_table: str = Field(..., min_length=1)
    target_column: str = Field(..., min_length=1)
    cardinality: Optional[str] = "one-to-many"


class RelationshipActionResponse(BaseModel):
    success: bool
    message: str
    relationship_id: str
    status: str
    cardinality: str


class JoinGenerateRequest(BaseModel):
    table_a: str = Field(..., min_length=1)
    table_b: str = Field(..., min_length=1)
    join_type: Optional[str] = "INNER JOIN"
    source_column: Optional[str] = None
    target_column: Optional[str] = None


class JoinGenerateResponse(BaseModel):
    sql: str
    table_a: str
    table_b: str
    join_type: str
    join_condition: str
    explanation: str
    is_ambiguous: bool = False
    available_relationships: List[RelationshipVisualizerInfo] = Field(default_factory=list)
