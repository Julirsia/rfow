from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings, resolve_dataset_config_path


def normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())


class DatasetCatalogEntry(BaseModel):
    name: str
    display_name: str
    ragflow_name: Optional[str] = None
    vendor: Optional[str] = None
    doc_type: Optional[str] = None
    description: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("aliases")
    @classmethod
    def normalize_alias_list(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized

    def user_inputs(self) -> list[str]:
        values = [self.name, self.display_name]
        if self.ragflow_name:
            values.append(self.ragflow_name)
        values.extend(self.aliases)
        seen: set[str] = set()
        ordered: list[str] = []
        for item in values:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def ragflow_lookup_names(self) -> list[str]:
        values = [self.ragflow_name or self.display_name, self.display_name, self.name]
        seen: set[str] = set()
        ordered: list[str] = []
        for item in values:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered


class DatasetCatalog(BaseModel):
    datasets: list[DatasetCatalogEntry]

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatasetCatalog":
        path = resolve_dataset_config_path(settings)
        return cls.from_path(path)

    @classmethod
    def from_path(cls, path: Path) -> "DatasetCatalog":
        if not path.exists():
            raise RuntimeError(f"Dataset config file not found: {path}")
        with path.open("r", encoding="utf-8") as file_obj:
            raw = yaml.safe_load(file_obj) or {}
        catalog = cls.model_validate(raw)
        catalog.validate_collisions()
        return catalog

    def enabled_datasets(self) -> list[DatasetCatalogEntry]:
        return [item for item in self.datasets if item.enabled]

    def validate_collisions(self) -> None:
        seen: dict[str, str] = {}
        upstream_seen: dict[str, str] = {}
        for entry in self.enabled_datasets():
            for key in [entry.name, entry.display_name, *entry.aliases]:
                normalized = normalize_name(key)
                owner = seen.get(normalized)
                if owner and owner != entry.name:
                    raise RuntimeError(
                        f"Dataset identifier collision: '{key}' conflicts between '{owner}' and '{entry.name}'."
                    )
                seen[normalized] = entry.name
            upstream_key = normalize_name(entry.ragflow_name or entry.display_name)
            upstream_owner = upstream_seen.get(upstream_key)
            if upstream_owner and upstream_owner != entry.name:
                raise RuntimeError(
                    f"Dataset upstream collision: '{entry.name}' and '{upstream_owner}' resolve to the same RAGFlow dataset name."
                )
            upstream_seen[upstream_key] = entry.name
