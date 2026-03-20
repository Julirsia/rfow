from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.services.dataset_catalog import DatasetCatalog
from app.services.dataset_resolver import DatasetResolver
from app.services.download_tokens import DownloadTokenSigner, SourceRefSigner
from app.services.ragflow_client import RagflowClient


def get_app_settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_ragflow_client() -> RagflowClient:
    return RagflowClient(get_settings())


@lru_cache(maxsize=1)
def get_dataset_catalog() -> DatasetCatalog:
    return DatasetCatalog.from_settings(get_settings())


@lru_cache(maxsize=1)
def get_download_token_signer() -> DownloadTokenSigner:
    settings = get_settings()
    secret = settings.download_token_secret or settings.ragflow_api_key
    return DownloadTokenSigner(secret=secret, ttl_seconds=settings.download_token_ttl_seconds)


@lru_cache(maxsize=1)
def get_source_ref_signer() -> SourceRefSigner:
    settings = get_settings()
    secret = settings.download_token_secret or settings.ragflow_api_key
    return SourceRefSigner(secret=secret, ttl_seconds=settings.source_ref_ttl_seconds)


@lru_cache(maxsize=1)
def get_dataset_resolver() -> DatasetResolver:
    return DatasetResolver(
        settings=get_settings(),
        catalog=get_dataset_catalog(),
        ragflow_client=get_ragflow_client(),
    )
