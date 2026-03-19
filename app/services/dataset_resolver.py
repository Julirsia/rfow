from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.cache import TTLCache
from app.config import Settings
from app.errors import api_error
from app.models.datasets import DatasetItem
from app.services.dataset_catalog import DatasetCatalog, DatasetCatalogEntry, normalize_name
from app.services.ragflow_client import RagflowClient


@dataclass
class ResolvedDataset:
    entry: DatasetCatalogEntry
    dataset_id: str
    runtime_name: str

    @property
    def public_name(self) -> str:
        return self.entry.name


class DatasetResolver:
    def __init__(self, *, settings: Settings, catalog: DatasetCatalog, ragflow_client: RagflowClient) -> None:
        self.settings = settings
        self.catalog = catalog
        self.ragflow_client = ragflow_client
        self._cache = TTLCache[list[dict[str, Any]]](settings.dataset_cache_ttl_seconds)
        self._stale_runtime_datasets: list[dict[str, Any]] = []

    async def list_datasets(self) -> list[DatasetItem]:
        runtime_datasets = await self._get_runtime_datasets()
        items: list[DatasetItem] = []
        for entry in self.catalog.enabled_datasets():
            matched = self._match_runtime_dataset(entry, runtime_datasets)
            items.append(
                DatasetItem(
                    name=entry.name,
                    display_name=entry.display_name,
                    aliases=entry.aliases,
                    status="ready" if matched else "missing",
                )
            )
        return items

    async def resolve(self, raw_dataset_name: str) -> ResolvedDataset:
        entry = self._resolve_catalog_entry(raw_dataset_name)
        runtime_datasets = await self._get_runtime_datasets()
        matched = self._match_runtime_dataset(entry, runtime_datasets)
        if matched is None:
            runtime_datasets = await self._refresh_runtime_datasets()
            matched = self._match_runtime_dataset(entry, runtime_datasets)
        if matched is None and self._stale_runtime_datasets:
            matched = self._match_runtime_dataset(entry, self._stale_runtime_datasets)
        if matched is None:
            raise api_error(
                status_code=404,
                code="dataset_not_found",
                message=f"Dataset '{entry.name}' is configured but not available in RAGFlow.",
                candidates=[item.name for item in await self.list_datasets() if item.status == "ready"],
            )
        dataset_id = str(matched.get("id") or "")
        if not dataset_id:
            raise api_error(status_code=502, code="dataset_missing_id", message="Resolved dataset does not include an ID.")
        return ResolvedDataset(entry=entry, dataset_id=dataset_id, runtime_name=str(matched.get("name") or entry.display_name))

    async def resolve_all_ready(self) -> list[ResolvedDataset]:
        runtime_datasets = await self._get_runtime_datasets()
        resolved: list[ResolvedDataset] = []
        seen_dataset_ids: dict[str, str] = {}
        for entry in self.catalog.enabled_datasets():
            matched = self._match_runtime_dataset(entry, runtime_datasets)
            if matched is None:
                continue
            dataset_id = str(matched.get("id") or "")
            if not dataset_id:
                continue
            owner = seen_dataset_ids.get(dataset_id)
            if owner and owner != entry.name:
                raise api_error(
                    status_code=500,
                    code="dataset_config_duplicate_upstream",
                    message=f"Datasets '{owner}' and '{entry.name}' resolve to the same upstream dataset.",
                )
            seen_dataset_ids[dataset_id] = entry.name
            resolved.append(
                ResolvedDataset(entry=entry, dataset_id=dataset_id, runtime_name=str(matched.get("name") or entry.display_name))
            )
        return resolved

    def _resolve_catalog_entry(self, raw_dataset_name: str) -> DatasetCatalogEntry:
        candidates = self.catalog.enabled_datasets()
        exact_name = [entry for entry in candidates if entry.name == raw_dataset_name]
        if len(exact_name) == 1:
            return exact_name[0]
        exact_display = [entry for entry in candidates if entry.display_name == raw_dataset_name]
        if len(exact_display) == 1:
            return exact_display[0]
        exact_ragflow = [entry for entry in candidates if entry.ragflow_name == raw_dataset_name]
        if len(exact_ragflow) == 1:
            return exact_ragflow[0]
        exact_alias = [entry for entry in candidates if raw_dataset_name in entry.aliases]
        if len(exact_alias) == 1:
            return exact_alias[0]

        lowered = raw_dataset_name.lower()
        ci_matches = [
            entry
            for entry in candidates
            if lowered in {item.lower() for item in entry.user_inputs()}
        ]
        if len(ci_matches) == 1:
            return ci_matches[0]
        if len(ci_matches) > 1:
            raise api_error(
                status_code=400,
                code="dataset_ambiguous",
                message=f"Dataset name '{raw_dataset_name}' is ambiguous.",
                candidates=[item.name for item in ci_matches],
            )

        normalized = normalize_name(raw_dataset_name)
        normalized_matches = [
            entry
            for entry in candidates
            if normalized in {normalize_name(item) for item in entry.user_inputs()}
        ]
        if len(normalized_matches) == 1:
            return normalized_matches[0]
        if len(normalized_matches) > 1:
            raise api_error(
                status_code=400,
                code="dataset_ambiguous",
                message=f"Dataset name '{raw_dataset_name}' is ambiguous.",
                candidates=[item.name for item in normalized_matches],
            )
        raise api_error(
            status_code=404,
            code="dataset_not_found",
            message=f"Unknown dataset name: {raw_dataset_name}",
            candidates=[entry.name for entry in candidates],
        )

    async def _get_runtime_datasets(self) -> list[dict[str, Any]]:
        cached = self._cache.get("datasets")
        if cached is not None:
            return cached
        return await self._refresh_runtime_datasets()

    async def _refresh_runtime_datasets(self) -> list[dict[str, Any]]:
        runtime_datasets = await self.ragflow_client.list_datasets()
        self._stale_runtime_datasets = runtime_datasets
        self._cache.set("datasets", runtime_datasets)
        return runtime_datasets

    def _match_runtime_dataset(
        self,
        entry: DatasetCatalogEntry,
        runtime_datasets: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        runtime_names = [str(item.get("name") or "") for item in runtime_datasets]
        for lookup_name in entry.ragflow_lookup_names():
            exact = [item for item in runtime_datasets if str(item.get("name") or "") == lookup_name]
            if len(exact) == 1:
                return exact[0]
            lowered = [item for item in runtime_datasets if str(item.get("name") or "").lower() == lookup_name.lower()]
            if len(lowered) == 1:
                return lowered[0]
            normalized = [item for item in runtime_datasets if normalize_name(str(item.get("name") or "")) == normalize_name(lookup_name)]
            if len(normalized) == 1:
                return normalized[0]
        if len(runtime_names) == 1 and normalize_name(runtime_names[0]) == normalize_name(entry.name):
            return runtime_datasets[0]
        return None
