from pydantic import BaseModel, Field, PositiveInt, constr
from enum import Enum
from datetime import datetime

class ModelName(str, Enum):
    GPT4_O = "gpt-4o"
    GPT4_O_MINI = "gpt-4o-mini"

class QueryInput(BaseModel):
    question: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = Field(default=None)
    model: ModelName = Field(default=ModelName.GPT4_O_MINI)

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
    upload_timestamp: datetime

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
