from datetime import datetime
from enum import StrEnum
from typing import Annotated

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


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    last_active: datetime


class ChatMessage(BaseModel):
    role: str
    content: str


class DeleteFileRequest(BaseModel):
    file_id: PositiveInt


class UploadDocumentResponse(BaseModel):
    message: str
    file_id: int


class DeleteDocumentResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
