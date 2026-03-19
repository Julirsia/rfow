from app.services.download_tokens import DownloadTokenSigner


def test_download_proxy_streams_document(client) -> None:
    search_response = client.post("/search_dataset", json={"question": "연차", "dataset_name": "hr_handbook"})
    download_url = search_response.json()["sources"][0]["source_download_url"]
    path = download_url.replace("https://wrapper.example.com", "")

    response = client.get(path)

    assert response.status_code == 200
    assert response.content == b"leave file"
    assert "attachment;" in response.headers["content-disposition"]


def test_expired_download_token_is_rejected(client) -> None:
    signer = DownloadTokenSigner(secret="test-secret", ttl_seconds=900)
    expired_token = signer._encode(
        {
            "dataset_id": "ds-hr",
            "document_id": "doc-leave",
            "filename": "leave_policy.pdf",
            "exp": 1,
        }
    )

    response = client.get(f"/_downloads/{expired_token}")

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "download_token_expired"


def test_invalid_download_token_is_rejected(client) -> None:
    response = client.get("/_downloads/not-a-real-token")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_download_token"
