from __future__ import annotations

import html
import re
from typing import Any, Callable

from app.config import Settings
from app.models.common import EvidenceChunk, SourceItem, SourceSearchRef
from app.models.search import SearchAllResponse, SearchDatasetResponse, SearchSourceResponse
from app.services.dataset_resolver import ResolvedDataset


WHITESPACE_RE = re.compile(r"\s+")
HTML_RE = re.compile(r"<[^>]+>")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(clean_text(item) for item in value if clean_text(item))
    if isinstance(value, dict):
        return " ".join(clean_text(item) for item in value.values() if clean_text(item))
    text = html.unescape(str(value))
    text = HTML_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    clipped = value[: max(limit - 1, 0)].rstrip()
    return f"{clipped}…"


def _extract_chunks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_chunks = payload.get("chunks")
    if isinstance(raw_chunks, list):
        return [item for item in raw_chunks if isinstance(item, dict)]
    if isinstance(raw_chunks, dict):
        return [item for item in raw_chunks.values() if isinstance(item, dict)]
    return []


def _doc_name_map(payload: dict[str, Any]) -> dict[str, str]:
    raw_doc_aggs = payload.get("doc_aggs") or []
    mapping: dict[str, str] = {}
    if isinstance(raw_doc_aggs, list):
        for item in raw_doc_aggs:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id") or "")
            doc_name = str(item.get("doc_name") or "")
            if doc_id and doc_name:
                mapping[doc_id] = doc_name
    elif isinstance(raw_doc_aggs, dict):
        for item in raw_doc_aggs.values():
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id") or "")
            doc_name = str(item.get("doc_name") or "")
            if doc_id and doc_name:
                mapping[doc_id] = doc_name
    return mapping


def _document_name(chunk: dict[str, Any], doc_name_map: dict[str, str]) -> str:
    for key in ("document_name", "document_keyword"):
        value = clean_text(chunk.get(key))
        if value:
            return value
    doc_id = str(chunk.get("document_id") or "")
    if doc_id and doc_id in doc_name_map:
        return doc_name_map[doc_id]
    return "unknown-document"


def _chunk_score(chunk: dict[str, Any]) -> float:
    raw_value = chunk.get("similarity")
    if raw_value is None:
        raw_value = chunk.get("score", 0.0)
    try:
        return round(float(raw_value), 3)
    except Exception:
        return 0.0


def _chunk_dataset_id(chunk: dict[str, Any]) -> str:
    return str(chunk.get("dataset_id") or chunk.get("kb_id") or "")


def _snippet(chunk: dict[str, Any], *, limit: int) -> str:
    for key in ("content", "content_with_weight", "highlight", "content_ltks"):
        value = clean_text(chunk.get(key))
        if value:
            return truncate_text(value, limit)
    return ""


def _source_label(dataset_name: str, document_name: str) -> str:
    return f"{dataset_name} / {document_name}"


def normalize_search_dataset_response(
    *,
    query: str,
    resolved_dataset: ResolvedDataset,
    retrieval_payload: dict[str, Any],
    settings: Settings,
    download_url_builder: Callable[[str, str, str], str],
    source_ref_builder: Callable[[str, str, str, str], str],
) -> SearchDatasetResponse:
    normalized = _normalize_common(
        retrieval_payload=retrieval_payload,
        settings=settings,
        dataset_id_to_name={resolved_dataset.dataset_id: resolved_dataset.public_name},
        download_url_builder=download_url_builder,
        source_ref_builder=source_ref_builder,
    )
    return SearchDatasetResponse(
        query=query,
        selected_dataset=resolved_dataset.public_name,
        found=bool(normalized["chunks"]),
        result_count=len(normalized["chunks"]),
        context_text=normalized["context_text"],
        chunks=normalized["chunks"],
        sources=normalized["sources"],
    )


def normalize_search_all_response(
    *,
    query: str,
    resolved_datasets: list[ResolvedDataset],
    retrieval_payload: dict[str, Any],
    settings: Settings,
    download_url_builder: Callable[[str, str, str], str],
    source_ref_builder: Callable[[str, str, str, str], str],
) -> SearchAllResponse:
    dataset_id_to_name = {item.dataset_id: item.public_name for item in resolved_datasets}
    normalized = _normalize_common(
        retrieval_payload=retrieval_payload,
        settings=settings,
        dataset_id_to_name=dataset_id_to_name,
        download_url_builder=download_url_builder,
        source_ref_builder=source_ref_builder,
    )
    matched_datasets = sorted({chunk.dataset_name for chunk in normalized["chunks"]})
    return SearchAllResponse(
        query=query,
        matched_datasets=matched_datasets,
        found=bool(normalized["chunks"]),
        result_count=len(normalized["chunks"]),
        context_text=normalized["context_text"],
        chunks=normalized["chunks"],
        sources=normalized["sources"],
    )


def normalize_search_source_response(
    *,
    query: str,
    source_ref: SourceSearchRef,
    retrieval_payload: dict[str, Any],
    settings: Settings,
    download_url_builder: Callable[[str, str, str], str],
    source_ref_builder: Callable[[str, str, str, str], str],
) -> SearchSourceResponse:
    normalized = _normalize_common(
        retrieval_payload=retrieval_payload,
        settings=settings,
        dataset_id_to_name={source_ref.dataset_id: source_ref.dataset_name},
        download_url_builder=download_url_builder,
        source_ref_builder=source_ref_builder,
        document_scope=(source_ref.dataset_id, source_ref.document_id),
    )
    return SearchSourceResponse(
        query=query,
        selected_dataset=source_ref.dataset_name,
        selected_document=source_ref.document_name,
        found=bool(normalized["chunks"]),
        result_count=len(normalized["chunks"]),
        context_text=normalized["context_text"],
        chunks=normalized["chunks"],
        sources=normalized["sources"],
    )


def _normalize_common(
    *,
    retrieval_payload: dict[str, Any],
    settings: Settings,
    dataset_id_to_name: dict[str, str],
    download_url_builder: Callable[[str, str, str], str],
    source_ref_builder: Callable[[str, str, str, str], str],
    document_scope: tuple[str, str] | None = None,
) -> dict[str, Any]:
    raw_chunks = _extract_chunks(retrieval_payload)
    doc_name_map = _doc_name_map(retrieval_payload)
    deduped: dict[tuple[str, str, str], EvidenceChunk] = {}

    for chunk in raw_chunks:
        document_id = str(chunk.get("document_id") or "")
        if not document_id:
            continue
        dataset_id = _chunk_dataset_id(chunk)
        if document_scope and (dataset_id, document_id) != document_scope:
            continue
        dataset_name = dataset_id_to_name.get(dataset_id)
        if not dataset_name:
            continue
        document_name = _document_name(chunk, doc_name_map)
        snippet = _snippet(chunk, limit=settings.snippet_max_chars)
        if not snippet:
            continue
        score = _chunk_score(chunk)
        source_url = download_url_builder(dataset_id, document_id, document_name)
        source_ref = source_ref_builder(dataset_id, dataset_name, document_id, document_name)
        normalized_key = (dataset_name, document_name.lower(), snippet.lower())
        evidence = EvidenceChunk(
            rank=0,
            dataset_name=dataset_name,
            document_name=document_name,
            snippet=snippet,
            score=score,
            source_label=_source_label(dataset_name, document_name),
            source_ref=source_ref,
            source_download_url=source_url,
        )
        existing = deduped.get(normalized_key)
        if existing is None or evidence.score > existing.score:
            deduped[normalized_key] = evidence

    ordered = sorted(deduped.values(), key=lambda item: (-item.score, item.document_name.lower()))
    ranked_chunks = [
        chunk.model_copy(update={"rank": index})
        for index, chunk in enumerate(ordered[: settings.max_top_k], start=1)
    ]

    seen_sources: set[tuple[str, str, str]] = set()
    sources: list[SourceItem] = []
    for chunk in ranked_chunks:
        key = (chunk.dataset_name, chunk.document_name, chunk.source_download_url)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append(
            SourceItem(
                dataset_name=chunk.dataset_name,
                document_name=chunk.document_name,
                source_label=chunk.source_label,
                source_ref=chunk.source_ref,
                source_download_url=chunk.source_download_url,
            )
        )

    context_parts: list[str] = []
    current_length = 0
    for chunk in ranked_chunks[:4]:
        part = f"[{chunk.rank}] {chunk.document_name}\n{chunk.snippet}"
        projected = current_length + len(part) + (2 if context_parts else 0)
        if projected > settings.context_max_chars and context_parts:
            break
        if projected > settings.context_max_chars:
            part = truncate_text(part, settings.context_max_chars)
        context_parts.append(part)
        current_length = sum(len(item) for item in context_parts) + max(len(context_parts) - 1, 0) * 2

    return {
        "chunks": ranked_chunks,
        "sources": sources,
        "context_text": "\n\n".join(context_parts),
    }
