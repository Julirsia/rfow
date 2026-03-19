from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class Settings(BaseModel):
    ragflow_base_url: HttpUrl
    ragflow_api_key: str
    dataset_config_path: str = "config/datasets.yaml"
    public_base_url: Optional[HttpUrl] = None
    request_timeout_seconds: int = 20
    dataset_cache_ttl_seconds: int = 60
    default_top_k: int = 4
    max_top_k: int = 8
    snippet_max_chars: int = 320
    context_max_chars: int = 1500
    download_token_ttl_seconds: int = 900
    download_token_secret: Optional[str] = None
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("default_top_k")
    @classmethod
    def validate_default_top_k(cls, value: int) -> int:
        if value < 1:
            raise ValueError("default_top_k must be >= 1")
        return value

    @field_validator("max_top_k")
    @classmethod
    def validate_max_top_k(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_top_k must be >= 1")
        return value

    @model_validator(mode="after")
    def validate_thresholds(self) -> "Settings":
        if self.default_top_k > self.max_top_k:
            raise ValueError("default_top_k must be <= max_top_k")
        if self.snippet_max_chars < 50:
            raise ValueError("snippet_max_chars must be >= 50")
        if self.context_max_chars < self.snippet_max_chars:
            raise ValueError("context_max_chars must be >= snippet_max_chars")
        return self


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _split_csv(raw_value: Optional[str]) -> list[str]:
    if not raw_value:
        return ["*"]
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    settings = Settings(
        ragflow_base_url=_env("RAGFLOW_BASE_URL"),
        ragflow_api_key=_env("RAGFLOW_API_KEY"),
        dataset_config_path=_env("DATASET_CONFIG_PATH", "config/datasets.yaml"),
        public_base_url=os.getenv("PUBLIC_BASE_URL"),
        request_timeout_seconds=int(_env("REQUEST_TIMEOUT_SECONDS", "20")),
        dataset_cache_ttl_seconds=int(_env("DATASET_CACHE_TTL_SECONDS", "60")),
        default_top_k=int(_env("DEFAULT_TOP_K", "4")),
        max_top_k=int(_env("MAX_TOP_K", "8")),
        snippet_max_chars=int(_env("SNIPPET_MAX_CHARS", "320")),
        context_max_chars=int(_env("CONTEXT_MAX_CHARS", "1500")),
        download_token_ttl_seconds=int(_env("DOWNLOAD_TOKEN_TTL_SECONDS", "900")),
        download_token_secret=os.getenv("DOWNLOAD_TOKEN_SECRET"),
        cors_allowed_origins=_split_csv(os.getenv("CORS_ALLOWED_ORIGINS")),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings


def resolve_dataset_config_path(settings: Settings) -> Path:
    raw_path = Path(settings.dataset_config_path)
    if raw_path.is_absolute():
        return raw_path
    return Path.cwd() / raw_path


def settings_for_tests(**overrides: Any) -> Settings:
    defaults = {
        "ragflow_base_url": "https://ragflow.example.com",
        "ragflow_api_key": "ragflow_api_key",
        "dataset_config_path": "config/datasets.yaml",
        "public_base_url": "https://wrapper.example.com",
        "request_timeout_seconds": 20,
        "dataset_cache_ttl_seconds": 60,
        "default_top_k": 4,
        "max_top_k": 8,
        "snippet_max_chars": 320,
        "context_max_chars": 1500,
        "download_token_ttl_seconds": 900,
        "download_token_secret": "test-secret",
        "cors_allowed_origins": ["*"],
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return Settings(**defaults)
