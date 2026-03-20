from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TMP_DIR = Path(tempfile.mkdtemp(prefix="ow-ragflow-tests-"))
DATASET_CONFIG_PATH = TMP_DIR / "datasets.yaml"
DATASET_CONFIG_PATH.write_text(
    """datasets:
  - name: hr_handbook
    display_name: HR Handbook
    ragflow_name: HR Handbook
    aliases:
      - hr
      - handbook
      - 인사규정
    enabled: true
  - name: finance_policy
    display_name: Finance Policy
    ragflow_name: Finance Policy
    aliases:
      - finance
      - expense
    enabled: true
""",
    encoding="utf-8",
)

os.environ.setdefault("RAGFLOW_BASE_URL", "https://ragflow.example.com")
os.environ.setdefault("RAGFLOW_API_KEY", "ragflow_api_key")
os.environ.setdefault("DATASET_CONFIG_PATH", str(DATASET_CONFIG_PATH))
os.environ.setdefault("PUBLIC_BASE_URL", "https://wrapper.example.com")
os.environ.setdefault("DOWNLOAD_TOKEN_SECRET", "test-secret")

from app.config import get_settings, settings_for_tests
from app.deps import (
    get_app_settings,
    get_dataset_catalog,
    get_dataset_resolver,
    get_download_token_signer,
    get_ragflow_client,
    get_source_ref_signer,
)
from app.main import app
from app.services.dataset_catalog import DatasetCatalog
from app.services.dataset_resolver import DatasetResolver
from app.services.download_tokens import DownloadTokenSigner, SourceRefSigner


class FakeRagflowClient:
    def __init__(self) -> None:
        self.datasets = [
            {"id": "ds-hr", "name": "HR Handbook"},
            {"id": "ds-fin", "name": "Finance Policy"},
        ]
        self.documents = {
            "ds-hr": [
                {"id": "doc-leave", "name": "leave_policy.pdf", "run": "DONE"},
                {"id": "doc-overview", "name": "handbook_overview.pdf", "run": "DONE"},
            ],
            "ds-fin": [
                {"id": "doc-expense", "name": "expense_policy.pdf", "run": "DONE"},
            ],
        }
        self.retrieval_payload = {
            "chunks": [
                {
                    "content": "연차는 발생일 기준 1년 내 사용해야 하며 기간 내 사용하지 않은 경우 규정에 따라 처리됩니다.",
                    "document_id": "doc-leave",
                    "document_keyword": "leave_policy.pdf",
                    "kb_id": "ds-hr",
                    "similarity": 0.9321,
                },
                {
                    "content": "미사용 연차의 처리는 사내 규정과 법령 적용 범위에 따라 달라질 수 있습니다.",
                    "document_id": "doc-overview",
                    "document_keyword": "handbook_overview.pdf",
                    "kb_id": "ds-hr",
                    "similarity": 0.8842,
                },
            ],
            "doc_aggs": [
                {"doc_id": "doc-leave", "doc_name": "leave_policy.pdf", "count": 1},
                {"doc_id": "doc-overview", "doc_name": "handbook_overview.pdf", "count": 1},
            ],
            "total": 2,
        }
        self.downloads = {
            ("ds-hr", "doc-leave"): (b"leave file", {"content-type": "application/pdf", "content-disposition": 'attachment; filename="leave_policy.pdf"'}),
            ("ds-hr", "doc-overview"): (b"overview file", {"content-type": "application/pdf", "content-disposition": 'attachment; filename="handbook_overview.pdf"'}),
            ("ds-fin", "doc-expense"): (b"expense file", {"content-type": "application/pdf", "content-disposition": 'attachment; filename="expense_policy.pdf"'}),
        }
        self.health_ok = True
        self.retrieve_calls: list[dict[str, Any]] = []

    async def close(self) -> None:
        return None

    async def probe_healthz(self):
        if self.health_ok:
            return True, None
        return False, "healthz failed"

    async def list_datasets(self, *, page_size: int = 100):
        return list(self.datasets)

    async def list_documents(self, dataset_id: str, *, page_size: int):
        docs = list(self.documents.get(dataset_id, []))[:page_size]
        return docs, len(docs)

    async def retrieve(self, payload: dict[str, Any]):
        self.retrieve_calls.append(dict(payload))
        dataset_ids = payload.get("dataset_ids", [])
        question = str(payload.get("question") or "")
        if dataset_ids == ["ds-fin"] or "출장비" in question:
            return {
                "chunks": [
                    {
                        "content": "출장비는 사전 승인된 범위에서 정산하며 영수증 제출이 필요합니다.",
                        "document_id": "doc-expense",
                        "document_keyword": "expense_policy.pdf",
                        "kb_id": "ds-fin",
                        "similarity": 0.941,
                    }
                ],
                "doc_aggs": [{"doc_id": "doc-expense", "doc_name": "expense_policy.pdf", "count": 1}],
                "total": 1,
            }
        return self.retrieval_payload

    async def download_document(self, dataset_id: str, document_id: str):
        return self.downloads[(dataset_id, document_id)]


@pytest.fixture
def fake_ragflow_client() -> FakeRagflowClient:
    return FakeRagflowClient()


@pytest.fixture
def client(fake_ragflow_client: FakeRagflowClient) -> TestClient:
    get_settings.cache_clear()
    get_dataset_catalog.cache_clear()
    get_dataset_resolver.cache_clear()
    get_download_token_signer.cache_clear()
    get_source_ref_signer.cache_clear()
    get_ragflow_client.cache_clear()

    settings = settings_for_tests(dataset_config_path=str(DATASET_CONFIG_PATH))
    catalog = DatasetCatalog.from_path(DATASET_CONFIG_PATH)
    signer = DownloadTokenSigner(secret=settings.download_token_secret or settings.ragflow_api_key, ttl_seconds=settings.download_token_ttl_seconds)
    source_ref_signer = SourceRefSigner(secret=settings.download_token_secret or settings.ragflow_api_key, ttl_seconds=settings.source_ref_ttl_seconds)
    resolver = DatasetResolver(settings=settings, catalog=catalog, ragflow_client=fake_ragflow_client)

    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_ragflow_client] = lambda: fake_ragflow_client
    app.dependency_overrides[get_dataset_catalog] = lambda: catalog
    app.dependency_overrides[get_dataset_resolver] = lambda: resolver
    app.dependency_overrides[get_download_token_signer] = lambda: signer
    app.dependency_overrides[get_source_ref_signer] = lambda: source_ref_signer

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
