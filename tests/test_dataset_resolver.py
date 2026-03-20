from pathlib import Path

import pytest

from app.services.dataset_catalog import DatasetCatalog


def test_list_datasets_marks_ready_status(client) -> None:
    response = client.get("/datasets")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["datasets"][0]["status"] == "ready"


def test_documents_support_alias_resolution(client) -> None:
    response = client.get("/datasets/hr/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_name"] == "hr_handbook"
    assert body["documents"][0]["source_ref"]
    assert body["documents"][0]["source_download_url"].startswith("https://wrapper.example.com/_downloads/")


def test_unknown_dataset_returns_candidates(client) -> None:
    response = client.get("/datasets/unknown/documents")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "dataset_not_found"
    assert "hr_handbook" in detail["candidates"]


def test_duplicate_ragflow_name_collision_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "datasets.yaml"
    config_path.write_text(
        """datasets:
  - name: hr_one
    display_name: HR One
    ragflow_name: Shared Dataset
    aliases: [one]
    enabled: true
  - name: hr_two
    display_name: HR Two
    ragflow_name: Shared Dataset
    aliases: [two]
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as exc_info:
        DatasetCatalog.from_path(config_path)

    assert "same RAGFlow dataset name" in str(exc_info.value)
