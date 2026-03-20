from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.models.common import FlatResponseModel


class DatasetItem(FlatResponseModel):
    name: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    status: Literal["ready", "missing"]


class DatasetsResponse(FlatResponseModel):
    datasets: list[DatasetItem]
    total: int


class DatasetDocumentsQuery(FlatResponseModel):
    limit: int = 20

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("limit must be between 1 and 50")
        return value


class DatasetDocumentItem(FlatResponseModel):
    document_name: str
    status: str
    source_label: str
    source_ref: str
    source_download_url: str


class DatasetDocumentsResponse(FlatResponseModel):
    dataset_name: str
    documents: list[DatasetDocumentItem]
    total: int
