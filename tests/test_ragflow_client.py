import asyncio

import httpx

from app.config import settings_for_tests
from app.services.ragflow_client import RagflowClient


def test_ragflow_client_maps_401_to_auth_error() -> None:
    client = RagflowClient(settings_for_tests())

    async def fake_request(method, url, **kwargs):
        return httpx.Response(401, request=httpx.Request(method, url), json={"message": "unauthorized"})

    client._client.request = fake_request

    try:
        asyncio.run(client.list_datasets())
        assert False, "Expected auth failure"
    except Exception as exc:
        assert exc.status_code == 502
        assert exc.detail["code"] == "ragflow_auth_failed"
    finally:
        asyncio.run(client.close())


def test_ragflow_client_maps_timeout_to_gateway_timeout() -> None:
    client = RagflowClient(settings_for_tests())

    async def fake_request(method, url, **kwargs):
        raise httpx.TimeoutException("timeout")

    client._client.request = fake_request

    try:
        asyncio.run(client.list_datasets())
        assert False, "Expected timeout failure"
    except Exception as exc:
        assert exc.status_code == 504
        assert exc.detail["code"] == "ragflow_timeout"
    finally:
        asyncio.run(client.close())
