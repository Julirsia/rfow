from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator

from app.models.common import EvidenceChunk, FlatResponseModel, NonEmptyStr, SourceItem


class SearchDatasetRequest(FlatResponseModel):
    question: NonEmptyStr = Field(description="User question to search.")
    dataset_name: NonEmptyStr = Field(description="Public dataset name or alias. Never use dataset IDs.")
    top_k: Optional[int] = Field(default=None, description="Optional number of evidence chunks to return.")


class SearchAllRequest(FlatResponseModel):
    question: NonEmptyStr = Field(description="User question to search across all allowed datasets.")
    top_k: Optional[int] = Field(default=None, description="Optional number of evidence chunks to return.")


class SearchDatasetResponse(FlatResponseModel):
    query: str
    selected_dataset: str
    found: bool
    result_count: int
    context_text: str
    chunks: list[EvidenceChunk]
    sources: list[SourceItem]


class SearchAllResponse(FlatResponseModel):
    query: str
    matched_datasets: list[str]
    found: bool
    result_count: int
    context_text: str
    chunks: list[EvidenceChunk]
    sources: list[SourceItem]
