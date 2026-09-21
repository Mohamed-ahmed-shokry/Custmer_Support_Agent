from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator

from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.settings import settings


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


class SearchResponse(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)


class SourceInfo(BaseModel):
    file_id: int | None = None
    filename: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    preview: str


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


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    last_active: datetime
    preview: str = ""
    label: str | None = None


class SessionSearchResult(BaseModel):
    session_id: str
    label: str | None = None
    match_count: int
    preview: str = ""
    last_active: datetime
    matched_queries: list[str] = Field(default_factory=list)


class SessionSearchResponse(BaseModel):
    query: str
    results: list[SessionSearchResult] = Field(default_factory=list)


class RenameSessionRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


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

    @field_validator("session_id", mode="before")
    @classmethod
    def strip_session_id(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class FeedbackResponse(BaseModel):
    message: str
    feedback_id: int


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

