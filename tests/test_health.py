def test_health_is_ok_when_healthz_works(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ragflow_status"] == "ok"
    assert body["ragflow_probe"] == "healthz"


def test_health_falls_back_when_healthz_fails(client, fake_ragflow_client) -> None:
    fake_ragflow_client.health_ok = False

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ragflow_status"] == "degraded"
    assert body["ragflow_probe"] == "datasets_fallback"
