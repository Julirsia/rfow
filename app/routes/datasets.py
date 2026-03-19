from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.deps import get_dataset_resolver, get_download_token_signer, get_ragflow_client
from app.models.datasets import DatasetDocumentItem, DatasetDocumentsResponse, DatasetsResponse
from app.services.dataset_resolver import DatasetResolver
from app.services.download_tokens import DownloadTokenSigner
from app.services.ragflow_client import RagflowClient

router = APIRouter(tags=["datasets"])


def _base_url(request: Request, public_base_url: Optional[str]) -> str:
    if public_base_url:
        return public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _download_url(
    *,
    request: Request,
    signer: DownloadTokenSigner,
    dataset_id: str,
    document_id: str,
    filename: str,
    public_base_url: Optional[str],
) -> str:
    token = signer.sign(dataset_id=dataset_id, document_id=document_id, filename=filename)
    return f"{_base_url(request, public_base_url)}/_downloads/{token}"


@router.get(
    "/datasets",
    response_model=DatasetsResponse,
    operation_id="listDatasets",
    summary="List searchable datasets",
    description="Use this when you need the correct dataset name before searching. Returns public names and aliases only. Never returns dataset IDs.",
)
async def list_datasets(dataset_resolver: DatasetResolver = Depends(get_dataset_resolver)) -> DatasetsResponse:
    datasets = await dataset_resolver.list_datasets()
    return DatasetsResponse(datasets=datasets, total=len(datasets))


@router.get(
    "/datasets/{dataset_name}/documents",
    response_model=DatasetDocumentsResponse,
    operation_id="listDatasetDocuments",
    summary="List documents in one dataset",
    description="Use this only when the user asks what documents exist in a dataset or when document titles are needed before answering.",
)
async def list_dataset_documents(
    dataset_name: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    dataset_resolver: DatasetResolver = Depends(get_dataset_resolver),
    ragflow_client: RagflowClient = Depends(get_ragflow_client),
    signer: DownloadTokenSigner = Depends(get_download_token_signer),
) -> DatasetDocumentsResponse:
    resolved_dataset = await dataset_resolver.resolve(dataset_name)
    documents, total = await ragflow_client.list_documents(resolved_dataset.dataset_id, page_size=limit)
    public_base_url = None
    settings = dataset_resolver.settings
    if settings.public_base_url:
        public_base_url = str(settings.public_base_url)
    items: list[DatasetDocumentItem] = []
    for item in documents:
        document_name = str(item.get("name") or "unknown-document")
        document_id = str(item.get("id") or "")
        if not document_id:
            continue
        items.append(
            DatasetDocumentItem(
                document_name=document_name,
                status=str(item.get("run") or item.get("status") or "unknown"),
                source_label=f"{resolved_dataset.public_name} / {document_name}",
                source_download_url=_download_url(
                    request=request,
                    signer=signer,
                    dataset_id=resolved_dataset.dataset_id,
                    document_id=document_id,
                    filename=document_name,
                    public_base_url=public_base_url,
                ),
            )
        )
    return DatasetDocumentsResponse(dataset_name=resolved_dataset.public_name, documents=items, total=total)
