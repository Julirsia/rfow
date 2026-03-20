from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

from app.deps import (
    get_app_settings,
    get_dataset_resolver,
    get_download_token_signer,
    get_ragflow_client,
    get_source_ref_signer,
)
from app.errors import api_error
from app.models.search import (
    SearchAllRequest,
    SearchAllResponse,
    SearchDatasetRequest,
    SearchDatasetResponse,
    SearchSourceRequest,
    SearchSourceResponse,
)
from app.services.dataset_resolver import DatasetResolver
from app.services.download_tokens import DownloadTokenSigner, SourceRefSigner
from app.services.ragflow_client import RagflowClient
from app.services.retrieval_normalizer import (
    normalize_search_all_response,
    normalize_search_dataset_response,
    normalize_search_source_response,
)

router = APIRouter(tags=["search"])


def _effective_top_k(requested_top_k: Optional[int], *, default_top_k: int, max_top_k: int) -> int:
    if requested_top_k is None:
        return default_top_k
    if requested_top_k < 1 or requested_top_k > max_top_k:
        raise api_error(
            status_code=422,
            code="invalid_top_k",
            message=f"top_k must be between 1 and {max_top_k}.",
        )
    return requested_top_k


def _make_download_url_builder(
    *,
    request: Request,
    signer: DownloadTokenSigner,
    public_base_url: Optional[str],
):
    base_url = public_base_url.rstrip("/") if public_base_url else str(request.base_url).rstrip("/")

    def build(dataset_id: str, document_id: str, filename: str) -> str:
        token = signer.sign(dataset_id=dataset_id, document_id=document_id, filename=filename)
        return f"{base_url}/_downloads/{token}"

    return build


def _make_source_ref_builder(*, signer: SourceRefSigner):
    def build(dataset_id: str, dataset_name: str, document_id: str, document_name: str) -> str:
        return signer.sign(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            document_id=document_id,
            document_name=document_name,
        )

    return build


def _retrieval_payload(
    *,
    question: str,
    dataset_ids: list[str],
    top_k: int,
    document_ids: Optional[list[str]] = None,
) -> dict[str, object]:
    page_size = min(max(top_k * 2, 8), 16)
    payload: dict[str, object] = {
        "question": question,
        "dataset_ids": dataset_ids,
        "page": 1,
        "page_size": page_size,
        "similarity_threshold": 0.2,
        "vector_similarity_weight": 0.3,
        "top_k": 64,
        "highlight": False,
        "keyword": False,
        "use_kg": False,
        "toc_enhance": False,
    }
    if document_ids:
        payload["document_ids"] = document_ids
    return payload


@router.post(
    "/search_dataset",
    response_model=SearchDatasetResponse,
    operation_id="searchDataset",
    summary="Search one dataset and return grounded evidence",
    description="Preferred search tool when the user names a dataset. Input dataset_name must be a public dataset name or alias, never a dataset ID.",
)
async def search_dataset(
    payload: SearchDatasetRequest,
    request: Request,
    settings=Depends(get_app_settings),
    dataset_resolver: DatasetResolver = Depends(get_dataset_resolver),
    ragflow_client: RagflowClient = Depends(get_ragflow_client),
    signer: DownloadTokenSigner = Depends(get_download_token_signer),
    source_ref_signer: SourceRefSigner = Depends(get_source_ref_signer),
) -> SearchDatasetResponse:
    top_k = _effective_top_k(payload.top_k, default_top_k=settings.default_top_k, max_top_k=settings.max_top_k)
    resolved_dataset = await dataset_resolver.resolve(payload.dataset_name)
    response_payload = await ragflow_client.retrieve(
        _retrieval_payload(question=payload.question, dataset_ids=[resolved_dataset.dataset_id], top_k=top_k)
    )
    builder = _make_download_url_builder(
        request=request,
        signer=signer,
        public_base_url=str(settings.public_base_url) if settings.public_base_url else None,
    )
    source_ref_builder = _make_source_ref_builder(signer=source_ref_signer)
    normalized = normalize_search_dataset_response(
        query=payload.question,
        resolved_dataset=resolved_dataset,
        retrieval_payload=response_payload,
        settings=settings.model_copy(update={"max_top_k": top_k}),
        download_url_builder=builder,
        source_ref_builder=source_ref_builder,
    )
    return normalized


@router.post(
    "/search_all",
    response_model=SearchAllResponse,
    operation_id="searchAllDatasets",
    summary="Search across all allowed datasets",
    description="Use this only when the dataset is unknown or the user explicitly asks to search across all datasets. Prefer searchDataset whenever possible.",
)
async def search_all(
    payload: SearchAllRequest,
    request: Request,
    settings=Depends(get_app_settings),
    dataset_resolver: DatasetResolver = Depends(get_dataset_resolver),
    ragflow_client: RagflowClient = Depends(get_ragflow_client),
    signer: DownloadTokenSigner = Depends(get_download_token_signer),
    source_ref_signer: SourceRefSigner = Depends(get_source_ref_signer),
) -> SearchAllResponse:
    top_k = _effective_top_k(payload.top_k, default_top_k=settings.default_top_k, max_top_k=settings.max_top_k)
    resolved_datasets = await dataset_resolver.resolve_all_ready()
    if not resolved_datasets:
        raise api_error(status_code=404, code="dataset_not_found", message="No ready datasets are available.")
    response_payload = await ragflow_client.retrieve(
        _retrieval_payload(question=payload.question, dataset_ids=[item.dataset_id for item in resolved_datasets], top_k=top_k)
    )
    builder = _make_download_url_builder(
        request=request,
        signer=signer,
        public_base_url=str(settings.public_base_url) if settings.public_base_url else None,
    )
    source_ref_builder = _make_source_ref_builder(signer=source_ref_signer)
    return normalize_search_all_response(
        query=payload.question,
        resolved_datasets=resolved_datasets,
        retrieval_payload=response_payload,
        settings=settings.model_copy(update={"max_top_k": top_k}),
        download_url_builder=builder,
        source_ref_builder=source_ref_builder,
    )


@router.post(
    "/search_source",
    response_model=SearchSourceResponse,
    operation_id="searchSource",
    summary="Search inside one previously returned source document",
    description="Use this when you need more detail from one source document that was already returned by this server. Input source_ref must come from this server. Never invent file IDs or document IDs.",
)
async def search_source(
    payload: SearchSourceRequest,
    request: Request,
    settings=Depends(get_app_settings),
    ragflow_client: RagflowClient = Depends(get_ragflow_client),
    download_signer: DownloadTokenSigner = Depends(get_download_token_signer),
    source_ref_signer: SourceRefSigner = Depends(get_source_ref_signer),
) -> SearchSourceResponse:
    top_k = _effective_top_k(payload.top_k, default_top_k=settings.default_top_k, max_top_k=settings.max_top_k)
    source_ref = source_ref_signer.verify(payload.source_ref)
    response_payload = await ragflow_client.retrieve(
        _retrieval_payload(
            question=payload.question,
            dataset_ids=[source_ref.dataset_id],
            document_ids=[source_ref.document_id],
            top_k=top_k,
        )
    )
    download_url_builder = _make_download_url_builder(
        request=request,
        signer=download_signer,
        public_base_url=str(settings.public_base_url) if settings.public_base_url else None,
    )
    source_ref_builder = _make_source_ref_builder(signer=source_ref_signer)
    return normalize_search_source_response(
        query=payload.question,
        source_ref=source_ref,
        retrieval_payload=response_payload,
        settings=settings.model_copy(update={"max_top_k": top_k}),
        download_url_builder=download_url_builder,
        source_ref_builder=source_ref_builder,
    )
