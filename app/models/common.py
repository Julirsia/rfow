from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    candidates: list[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    dataset_name: str
    document_name: str
    source_label: str
    source_download_url: str


class EvidenceChunk(BaseModel):
    rank: int
    dataset_name: str
    document_name: str
    snippet: str
    score: float
    source_label: str
    source_download_url: str


class FlatResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceDownloadRef(BaseModel):
    dataset_id: str
    document_id: str
    filename: str
    exp: int
    download: Optional[str] = None
