def test_search_dataset_returns_grounded_chunks_and_sources(client) -> None:
    response = client.post("/search_dataset", json={"question": "연차는 언제 소멸돼?", "dataset_name": "hr_handbook"})

    assert response.status_code == 200
    body = response.json()
    assert body["selected_dataset"] == "hr_handbook"
    assert body["found"] is True
    assert body["result_count"] == 2
    assert "leave_policy.pdf" in body["context_text"]
    assert body["chunks"][0]["rank"] == 1
    assert body["chunks"][0]["source_ref"]
    assert body["chunks"][0]["source_download_url"].startswith("https://wrapper.example.com/_downloads/")
    assert body["sources"][0]["document_name"] == "leave_policy.pdf"
    assert body["sources"][0]["source_ref"] == body["chunks"][0]["source_ref"]


def test_search_all_returns_matched_datasets(client) -> None:
    response = client.post("/search_all", json={"question": "출장비 정산 기준이 뭐야?", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["matched_datasets"] == ["finance_policy"]
    assert body["chunks"][0]["dataset_name"] == "finance_policy"


def test_search_dataset_returns_empty_when_nothing_found(client, fake_ragflow_client) -> None:
    fake_ragflow_client.retrieval_payload = {"chunks": [], "doc_aggs": [], "total": 0}

    response = client.post("/search_dataset", json={"question": "없는 질문", "dataset_name": "hr_handbook"})

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["result_count"] == 0
    assert body["chunks"] == []
    assert body["sources"] == []
    assert body["context_text"] == ""


def test_search_dataset_rejects_top_k_out_of_range(client) -> None:
    response = client.post("/search_dataset", json={"question": "연차", "dataset_name": "hr_handbook", "top_k": 99})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_top_k"


def test_search_source_restricts_results_to_one_document(client, fake_ragflow_client) -> None:
    initial = client.post("/search_dataset", json={"question": "연차는 언제 소멸돼?", "dataset_name": "hr_handbook"})
    source_ref = initial.json()["sources"][0]["source_ref"]

    response = client.post(
        "/search_source",
        json={"question": "연차 사용 기한만 더 자세히 찾아줘", "source_ref": source_ref, "top_k": 4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_dataset"] == "hr_handbook"
    assert body["selected_document"] == "leave_policy.pdf"
    assert body["result_count"] == 1
    assert body["chunks"][0]["document_name"] == "leave_policy.pdf"
    assert "handbook_overview.pdf" not in body["context_text"]
    assert fake_ragflow_client.retrieve_calls[-1]["document_ids"] == ["doc-leave"]


def test_search_source_rejects_invalid_source_ref(client) -> None:
    response = client.post("/search_source", json={"question": "다시 찾아줘", "source_ref": "not-a-real-ref"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_source_ref"
