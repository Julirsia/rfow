from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.deps import get_download_token_signer, get_ragflow_client
from app.services.download_tokens import DownloadTokenSigner
from app.services.ragflow_client import RagflowClient

router = APIRouter(tags=["downloads"])


@router.get("/_downloads/{token}", include_in_schema=False)
async def download_source_document(
    token: str,
    signer: DownloadTokenSigner = Depends(get_download_token_signer),
    ragflow_client: RagflowClient = Depends(get_ragflow_client),
) -> Response:
    payload = signer.verify(token)
    content, headers = await ragflow_client.download_document(payload.dataset_id, payload.document_id)
    filename = payload.filename
    disposition = headers.get("content-disposition") or f'attachment; filename="{filename}"'
    return Response(
        content=content,
        media_type=headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": disposition},
    )
