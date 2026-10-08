from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator, model_validator

from api import db_utils
from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.macros import extract_template_variables
from api.settings import settings


class ChunkingStrategy(StrEnum):
    RECURSIVE = "recursive"
    MARKDOWN = "markdown"
    SEMANTIC = "semantic"


class ModelName(StrEnum):
    GPT4_O = "gpt-4o"
    GPT4_O_MINI = "gpt-4o-mini"


DEFAULT_MODEL = ModelName.GPT4_O_MINI


def model_from_value(value: str | None) -> ModelName:
    try:
        return ModelName(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_MODEL


NonEmptyString = Annotated[str, Field(min_length=1)]


class QueryInput(BaseModel):
    question: NonEmptyString
    session_id: str | None = Field(default=None)
    model: ModelName = Field(default_factory=lambda: model_from_value(settings.default_model))
    file_ids: list[PositiveInt] | None = Field(default=None, max_length=50)
    source_filename: str | None = Field(default=None, max_length=255)
    use_hybrid: bool | None = Field(default=None)
    collections: list[str] | None = Field(default=None, max_length=20)
    expand_query: bool | None = Field(default=None)
    rerank: bool | None = Field(default=None)
    use_cross_encoder_rerank: bool | None = Field(default=None)
    cross_encoder_model: str | None = Field(default=None, max_length=100)

    @field_validator("collections", mode="before")
    @classmethod
    def normalize_collections(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [normalize_collection(item) for item in v]

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("source_filename", mode="before")
    @classmethod
    def strip_source_filename(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v


class SearchInput(BaseModel):
    question: NonEmptyString
    k: int = Field(default_factory=lambda: settings.retriever_k, ge=1, le=50)
    file_ids: list[PositiveInt] | None = Field(default=None, max_length=50)
    source_filename: str | None = Field(default=None, max_length=255)
    use_hybrid: bool | None = Field(default=None)
    collections: list[str] | None = Field(default=None, max_length=20)
    expand_query: bool | None = Field(default=None)
    rerank: bool | None = Field(default=None)
    use_cross_encoder_rerank: bool | None = Field(default=None)
    cross_encoder_model: str | None = Field(default=None, max_length=100)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("collections", mode="before")
    @classmethod
    def normalize_collections(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [normalize_collection(item) for item in v]

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("source_filename", mode="before")
    @classmethod
    def strip_source_filename(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v


class SearchHit(BaseModel):
    rank: int
    preview: str
    file_id: int | None = None
    filename: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    collection: str | None = None
    score: float | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)


class SourceInfo(BaseModel):
    file_id: int | None = None
    filename: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    preview: str
    score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    session_id: str
    model: ModelName
    sources: list[SourceInfo] = Field(default_factory=list)


class DocumentInfo(BaseModel):
    id: int
    filename: str
    collection: str = DEFAULT_COLLECTION
    upload_timestamp: datetime


class DocumentChunkInfo(BaseModel):
    chunk_id: str
    chunk_index: int
    page: int | None = None
    preview: str
    content: str


class DocumentDetailResponse(BaseModel):
    id: int
    filename: str
    collection: str = DEFAULT_COLLECTION
    sha256: str | None = None
    upload_timestamp: datetime | None = None
    chunk_count: int
    chunks: list[DocumentChunkInfo] = Field(default_factory=list)
    chunking_strategy: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class RechunkDocumentRequest(BaseModel):
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = Field(default=1000, ge=100, le=4000)
    chunk_overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def validate_overlap_less_than_size(self) -> "RechunkDocumentRequest":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self


class CollectionDetailResponse(BaseModel):
    collection: str
    document_count: int
    chunk_count: int = 0
    file_formats: dict[str, int] = Field(default_factory=dict)
    earliest_upload: str | None = None
    latest_upload: str | None = None


class CollectionRechunkRequest(BaseModel):
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = Field(default=1000, ge=100, le=4000)
    chunk_overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def validate_overlap_less_than_size(self) -> "CollectionRechunkRequest":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self


class DocumentRechunkItem(BaseModel):
    file_id: int
    filename: str
    status: Literal["rechunked", "skipped", "error"]
    chunk_count: int = 0
    error_message: str | None = None


class CollectionRechunkResponse(BaseModel):
    message: str
    collection: str
    strategy: str
    chunk_size: int
    chunk_overlap: int
    total_documents: int
    rechunked_documents: int
    skipped_documents: int
    failed_documents: int
    total_chunks_created: int
    items: list[DocumentRechunkItem] = Field(default_factory=list)


class CollectionAnalyticsResponse(BaseModel):
    collection: str
    total_documents: int
    total_chunks: int
    avg_chunk_length: float = 0.0
    min_chunk_length: int = 0
    max_chunk_length: int = 0
    median_chunk_length: float = 0.0
    strategy_distribution: dict[str, int] = Field(default_factory=dict)
    length_histogram: dict[str, int] = Field(default_factory=dict)


VALID_SESSION_STATUSES = {"active", "resolved", "escalated", "closed"}
VALID_SESSION_PRIORITIES = {"urgent", "high", "medium", "low"}
DEFAULT_SESSION_PRIORITY = "medium"
MAX_SESSION_LABEL_LENGTH = 80
MAX_SESSION_TAGS_LENGTH = 200
MAX_SESSION_SUMMARY_LENGTH = 2000
MAX_RESOLUTION_NOTES_LENGTH = 2000
MAX_SLA_POLICY_NAME_LENGTH = 100
MAX_SLA_CATEGORY_LENGTH = 50


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    last_active: datetime
    preview: str = ""
    label: str | None = None
    status: str = "active"
    tags: str = ""
    summary: str | None = None
    resolution_notes: str | None = None
    priority: str = DEFAULT_SESSION_PRIORITY


class SessionSearchResult(BaseModel):
    session_id: str
    label: str | None = None
    status: str = "active"
    tags: str = ""
    match_count: int
    preview: str = ""
    last_active: datetime
    matched_queries: list[str] = Field(default_factory=list)
    priority: str = DEFAULT_SESSION_PRIORITY


class SessionSearchResponse(BaseModel):
    query: str
    results: list[SessionSearchResult] = Field(default_factory=list)


class UpdateSessionRequest(BaseModel):
    label: str | None = None
    status: str | None = None
    tags: str | list[str] | None = None
    summary: str | None = None
    resolution_notes: str | None = None
    priority: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Session label must not be blank.")
            if len(cleaned) > MAX_SESSION_LABEL_LENGTH:
                raise ValueError(
                    f"Session label must be at most {MAX_SESSION_LABEL_LENGTH} characters."
                )
            return cleaned
        return v

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned not in VALID_SESSION_STATUSES:
                raise ValueError(
                    f"Invalid session status '{cleaned}'. "
                    f"Must be one of: {sorted(VALID_SESSION_STATUSES)}."
                )
            return cleaned
        return v

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if len(cleaned) > MAX_SESSION_SUMMARY_LENGTH:
                raise ValueError(
                    f"Session summary must be at most {MAX_SESSION_SUMMARY_LENGTH} characters."
                )
            return cleaned
        return v

    @field_validator("resolution_notes", mode="before")
    @classmethod
    def validate_resolution_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if len(cleaned) > MAX_RESOLUTION_NOTES_LENGTH:
                raise ValueError(
                    f"Resolution notes must be at most {MAX_RESOLUTION_NOTES_LENGTH} characters."
                )
            return cleaned
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned not in VALID_SESSION_PRIORITIES:
                raise ValueError(
                    f"Invalid session priority '{cleaned}'. "
                    f"Must be one of: {sorted(VALID_SESSION_PRIORITIES)}."
                )
            return cleaned
        return v

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "UpdateSessionRequest":
        if (
            self.label is None
            and self.status is None
            and self.tags is None
            and self.summary is None
            and self.resolution_notes is None
            and self.priority is None
        ):
            raise ValueError(
                "At least one of 'label', 'status', 'tags', 'summary', 'resolution_notes', "
                "or 'priority' must be provided."
            )
        return self


class SessionSummaryRequest(BaseModel):
    model: str | None = None
    save_summary: bool = True


class SessionSummaryResponse(BaseModel):
    session_id: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    suggested_tags: list[str] = Field(default_factory=list)
    saved: bool = False


class TagCount(BaseModel):
    tag: str
    count: int


class SupportTriageAnalyticsResponse(BaseModel):
    total_sessions: int
    active_count: int
    resolved_count: int
    escalated_count: int
    closed_count: int
    resolution_rate: float
    escalation_rate: float
    avg_turns_per_session: float
    top_tags: list[TagCount] = Field(default_factory=list)
    priority_counts: dict[str, int] = Field(default_factory=dict)


class RenameSessionRequest(UpdateSessionRequest):
    label: str = Field(min_length=1, max_length=80)


class RenameCollectionRequest(BaseModel):
    collection: str = Field(min_length=1, max_length=64)

    @field_validator("collection", mode="before")
    @classmethod
    def normalize_collection_field(cls, v: str) -> str:
        return normalize_collection(v) if isinstance(v, str) else v


class RenameCollectionResponse(BaseModel):
    message: str
    collection: str
    documents: int
    chunks: int


class DeleteSessionResponse(BaseModel):
    message: str


class PruneSessionsResponse(BaseModel):
    message: str
    deleted_sessions: int


class FeedbackInput(BaseModel):
    session_id: NonEmptyString
    rating: Literal[1, -1]
    comment: str | None = None

    @field_validator("session_id", mode="before")
    @classmethod
    def strip_session_id(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None


class FeedbackResponse(BaseModel):
    message: str
    feedback_id: int


class FeedbackItem(BaseModel):
    id: int
    session_id: str
    rating: int
    comment: str | None = None
    created_at: str


class FeedbackListResponse(BaseModel):
    items: list[FeedbackItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class FeedbackAnalyticsResponse(BaseModel):
    total_feedback: int
    positive_feedback: int
    negative_feedback: int
    satisfaction_rate: float
    total_comments: int
    comment_rate: float
    recent_comments: list[FeedbackItem] = Field(default_factory=list)



class QuotaInfo(BaseModel):
    budget: int
    used: int
    remaining: int | None
    unlimited: bool


class StatsResponse(BaseModel):
    documents: int
    collections: int
    sessions: int
    messages: int
    feedback_up: int = 0
    feedback_down: int = 0


class ChatMessage(BaseModel):
    role: str
    content: str


class DeleteFileRequest(BaseModel):
    file_id: PositiveInt


class BulkDeleteFileRequest(BaseModel):
    file_ids: list[PositiveInt] = Field(min_length=1, max_length=50)


class BulkDeleteFileResult(BaseModel):
    file_id: int
    status: str
    detail: str | None = None


class BulkDeleteResponse(BaseModel):
    results: list[BulkDeleteFileResult] = Field(default_factory=list)
    deleted: int = 0
    failed: int = 0


class BulkDeleteSessionRequest(BaseModel):
    session_ids: list[NonEmptyString] = Field(min_length=1, max_length=50)

    @field_validator("session_ids")
    @classmethod
    def validate_session_ids(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        if not cleaned:
            raise ValueError("session_ids must contain at least one non-empty session ID.")
        return cleaned


class BulkDeleteSessionResult(BaseModel):
    session_id: str
    status: str
    detail: str | None = None


class BulkDeleteSessionResponse(BaseModel):
    results: list[BulkDeleteSessionResult] = Field(default_factory=list)
    deleted: int = 0
    failed: int = 0



class UploadDocumentResponse(BaseModel):
    message: str
    file_id: int


class BulkUploadItem(BaseModel):
    filename: str
    status: str
    file_id: int | None = None
    detail: str | None = None


class BulkUploadResponse(BaseModel):
    results: list[BulkUploadItem] = Field(default_factory=list)
    uploaded: int = 0
    failed: int = 0


class DeleteDocumentResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class ConfigResponse(BaseModel):
    app_name: str
    app_version: str
    default_model: str
    retriever_k: int
    max_history_turns: int
    max_upload_mb: int
    max_bulk_files: int
    use_hybrid_retriever: bool
    use_query_expansion: bool
    use_rerank: bool
    api_key_required: bool
    rate_limit_per_min: int
    token_budget_configured: bool
    supported_chunking_strategies: list[str] = Field(
        default_factory=lambda: ["recursive", "markdown"]
    )


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    events: str | list[str] | None = Field(default="*")
    secret: str | None = Field(default="", max_length=256)
    is_active: bool = Field(default=True)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return db_utils.normalize_webhook_url(v)

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: str | list[str] | None) -> str:
        return db_utils.normalize_webhook_events(v)

    @field_validator("secret", mode="before")
    @classmethod
    def validate_secret(cls, v: str | None) -> str:
        return db_utils.normalize_webhook_secret(v)


class WebhookUpdateRequest(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    events: str | list[str] | None = Field(default=None)
    secret: str | None = Field(default=None, max_length=256)
    is_active: bool | None = Field(default=None)
    reset_failures: bool = Field(default=False)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_webhook_url(v)

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: str | list[str] | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_webhook_events(v)

    @field_validator("secret")
    @classmethod
    def validate_secret(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_webhook_secret(v)


class WebhookResponse(BaseModel):
    id: int
    url: str
    events: str
    secret: str = ""
    is_active: bool
    failure_count: int
    created_at: str | None = None


class WebhookDeliveryLogItem(BaseModel):
    id: int
    webhook_id: int
    event: str
    url: str
    status_code: int | None = None
    success: bool
    payload_preview: str = ""
    error_message: str | None = None
    delivered_at: str | None = None


class WebhookDeliveryLogsResponse(BaseModel):
    items: list[WebhookDeliveryLogItem] = Field(default_factory=list)
    total: int = 0


class WebhookPingResponse(BaseModel):
    webhook_id: int
    url: str
    event: str
    status_code: int | None = None
    success: bool
    error: str | None = None


class MacroCreateRequest(BaseModel):
    title: str = Field(..., max_length=100)
    shortcut: str = Field(..., max_length=50)
    category: str = Field(default="General", max_length=50)
    content: str = Field(..., max_length=4000)
    tags: list[str] = Field(default_factory=list)
    status_action: str | None = Field(default=None)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return db_utils.normalize_macro_title(v)

    @field_validator("shortcut")
    @classmethod
    def validate_shortcut(cls, v: str) -> str:
        return db_utils.normalize_macro_shortcut(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return db_utils.normalize_macro_category(v)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        return db_utils.normalize_macro_content(v)

    @field_validator("status_action")
    @classmethod
    def validate_status_action(cls, v: str | None) -> str | None:
        return db_utils.normalize_macro_status_action(v)


class MacroUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    shortcut: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=50)
    content: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None)
    status_action: str | None = Field(default=None)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_macro_title(v)

    @field_validator("shortcut")
    @classmethod
    def validate_shortcut(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_macro_shortcut(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_macro_category(v)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_macro_content(v)

    @field_validator("status_action")
    @classmethod
    def validate_status_action(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return db_utils.normalize_macro_status_action(v)


class MacroResponse(BaseModel):
    id: int
    title: str
    shortcut: str
    category: str
    content: str
    tags: list[str] = Field(default_factory=list)
    status_action: str | None = None
    variables: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_variables(cls, data: Any) -> Any:
        if isinstance(data, dict):
            content = data.get("content", "")
            if "variables" not in data or not data["variables"]:
                data["variables"] = extract_template_variables(content)
        return data


class MacroRenderRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    fallback_defaults: bool = Field(default=True)


class MacroRenderResponse(BaseModel):
    macro_id: int
    rendered_content: str
    unresolved_variables: list[str] = Field(default_factory=list)
    status_action: str | None = None


class MacroApplyRequest(BaseModel):
    macro_id: int | None = Field(default=None)
    shortcut: str | None = Field(default=None)
    variables: dict[str, Any] = Field(default_factory=dict)
    fallback_defaults: bool = Field(default=True)
    update_status: bool = Field(default=True)
    append_tags: bool = Field(default=True)
    model: str = Field(default="macro")

    @model_validator(mode="after")
    def validate_identifier(self) -> "MacroApplyRequest":
        if self.macro_id is None and not self.shortcut:
            raise ValueError("Either macro_id or shortcut must be specified.")
        return self


class MacroApplyResponse(BaseModel):
    session_id: str
    macro_id: int
    macro_title: str
    rendered_content: str
    applied_status: str | None = None
    applied_tags: list[str] = Field(default_factory=list)
    unresolved_variables: list[str] = Field(default_factory=list)
    created_at: str | None = None


class MacroCategoriesResponse(BaseModel):
    categories: list[str] = Field(default_factory=list)


class MacroSuggestionItem(BaseModel):
    macro_id: int
    title: str
    shortcut: str
    category: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    match_reasons: list[str] = Field(default_factory=list)
    detected_intent: str = "unknown"
    status_action: str | None = None
    tags: list[str] = Field(default_factory=list)
    suggested_variables: dict[str, str] = Field(default_factory=dict)
    rendered_preview: str = ""


class MacroSuggestRequest(BaseModel):
    query: str
    session_id: str | None = None
    category: str | None = None
    top_k: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        cleaned = v.strip() if v else ""
        if not cleaned:
            raise ValueError("Query string cannot be empty.")
        return cleaned


class MacroSuggestResponse(BaseModel):
    query: str
    detected_intent: str
    intent_confidence: float
    extracted_variables: dict[str, str] = Field(default_factory=dict)
    suggestions: list[MacroSuggestionItem] = Field(default_factory=list)
    total_matches: int = 0


class SessionMacroSuggestionsResponse(BaseModel):
    session_id: str
    latest_query: str | None = None
    detected_intent: str = "unknown"
    extracted_variables: dict[str, str] = Field(default_factory=dict)
    suggestions: list[MacroSuggestionItem] = Field(default_factory=list)
    total_matches: int = 0


class SLAPolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SLA_POLICY_NAME_LENGTH)
    priority: str
    category: str = Field(default="general", max_length=MAX_SLA_CATEGORY_LENGTH)
    response_time_minutes: int = Field(gt=0)
    resolution_time_minutes: int = Field(gt=0)
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip() if isinstance(v, str) else ""
        if not cleaned:
            raise ValueError("SLA policy name must not be blank.")
        if len(cleaned) > MAX_SLA_POLICY_NAME_LENGTH:
            raise ValueError(
                f"SLA policy name exceeds max length {MAX_SLA_POLICY_NAME_LENGTH}."
            )
        return cleaned

    @field_validator("priority", mode="before")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        cleaned = v.strip().lower() if isinstance(v, str) else ""
        if cleaned not in VALID_SESSION_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{cleaned}'. Must be one of: {sorted(VALID_SESSION_PRIORITIES)}."
            )
        return cleaned

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, v: str | None) -> str:
        if v is None:
            return "general"
        cleaned = v.strip().lower() if isinstance(v, str) else "general"
        return cleaned or "general"

    @model_validator(mode="after")
    def validate_targets(self) -> "SLAPolicyCreateRequest":
        if self.resolution_time_minutes < self.response_time_minutes:
            raise ValueError(
                "resolution_time_minutes must be greater than or equal to response_time_minutes."
            )
        return self


class SLAPolicyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_SLA_POLICY_NAME_LENGTH)
    priority: str | None = None
    category: str | None = Field(default=None, max_length=MAX_SLA_CATEGORY_LENGTH)
    response_time_minutes: int | None = Field(default=None, gt=0)
    resolution_time_minutes: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip() if isinstance(v, str) else ""
        if not cleaned:
            raise ValueError("SLA policy name must not be blank.")
        return cleaned

    @field_validator("priority", mode="before")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().lower() if isinstance(v, str) else ""
        if cleaned not in VALID_SESSION_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{cleaned}'. Must be one of: {sorted(VALID_SESSION_PRIORITIES)}."
            )
        return cleaned

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().lower() if isinstance(v, str) else ""
        return cleaned or "general"

    @model_validator(mode="after")
    def validate_targets(self) -> "SLAPolicyUpdateRequest":
        if (
            self.name is None
            and self.priority is None
            and self.category is None
            and self.response_time_minutes is None
            and self.resolution_time_minutes is None
            and self.is_active is None
        ):
            raise ValueError("At least one SLA policy field must be provided for update.")
        if (
            self.response_time_minutes is not None
            and self.resolution_time_minutes is not None
            and self.resolution_time_minutes < self.response_time_minutes
        ):
            raise ValueError(
                "resolution_time_minutes must be greater than or equal to response_time_minutes."
            )
        return self


class SLAPolicyResponse(BaseModel):
    id: int
    name: str
    priority: str
    category: str
    response_time_minutes: int
    resolution_time_minutes: int
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


class SLAPoliciesListResponse(BaseModel):
    items: list[SLAPolicyResponse] = Field(default_factory=list)
    total: int = 0


class SessionSLAStatusResponse(BaseModel):
    session_id: str
    priority: str
    category: str
    status: str
    policy_id: int | None = None
    policy_name: str | None = None
    response_target_minutes: int
    resolution_target_minutes: int
    session_started_at: str | None = None
    first_response_at: str | None = None
    response_due_at: str | None = None
    resolution_due_at: str | None = None
    response_met: bool = False
    resolution_met: bool = False
    response_breached: bool = False
    resolution_breached: bool = False
    response_approaching: bool = False
    resolution_approaching: bool = False
    breach_status: Literal["met", "healthy", "approaching_breach", "breached"] = "healthy"
    minutes_to_response_deadline: float | None = None
    minutes_to_resolution_deadline: float | None = None


class SLAAlertItem(BaseModel):
    session_id: str
    priority: str
    category: str
    event: str
    breach_type: str
    deadline_due_at: str | None = None
    minutes_remaining: float | None = None
    webhooks_dispatched: int = 0


class SLAAlertEvaluateRequest(BaseModel):
    approaching_threshold_minutes: int = Field(default=30, gt=0)


class SLAAlertEvaluateResponse(BaseModel):
    total_sessions_checked: int
    alerts_triggered: int
    alerts: list[SLAAlertItem] = Field(default_factory=list)


class SLAComplianceAnalyticsResponse(BaseModel):
    total_tracked_sessions: int
    compliance_rate: float
    met_sessions: int
    healthy_sessions: int
    approaching_breach_sessions: int
    breached_sessions: int
    avg_first_response_minutes: float
    priority_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)




