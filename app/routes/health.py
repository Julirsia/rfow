from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_ragflow_client
from app.models.health import HealthResponse
from app.services.ragflow_client import RagflowClient

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="healthCheck",
    summary="Health check for the wrapper and upstream RAGFlow",
    description="Admin/debug only. Do not use this tool to answer user questions.",
)
async def health(ragflow_client: RagflowClient = Depends(get_ragflow_client)) -> HealthResponse:
    ok, error_message = await ragflow_client.probe_healthz()
    if ok:
        return HealthResponse(
            ok=True,
            wrapper_status="ok",
            ragflow_status="ok",
            ragflow_probe="healthz",
            ragflow_error=None,
        )
    try:
        await ragflow_client.list_datasets(page_size=1)
        return HealthResponse(
            ok=True,
            wrapper_status="degraded",
            ragflow_status="degraded",
            ragflow_probe="datasets_fallback",
            ragflow_error=error_message,
        )
    except Exception as exc:
        return HealthResponse(
            ok=False,
            wrapper_status="degraded",
            ragflow_status="unreachable",
            ragflow_probe="datasets_fallback",
            ragflow_error=str(getattr(exc, "detail", exc)),
        )
