from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.deps import get_app_settings, get_ragflow_client
from app.routes.datasets import router as datasets_router
from app.routes.downloads import router as downloads_router
from app.routes.health import router as health_router
from app.routes.search import router as search_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    try:
        client = get_ragflow_client()
    except RuntimeError:
        return
    await client.close()


app = FastAPI(
    title="RAGFlow Read-Only OpenAPI Thin Wrapper",
    version="0.1.0",
    description="Small-model-friendly read-only adapter for RAGFlow retrieval.",
    lifespan=lifespan,
)

try:
    settings = get_app_settings()
    cors_allowed_origins = settings.cors_allowed_origins
except RuntimeError:
    # Allow importing the app object for schema inspection even when runtime env is not configured yet.
    cors_allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(search_router)
app.include_router(downloads_router)
