from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.errors import api_error

logger = logging.getLogger(__name__)
RETRYABLE_METHODS = {"GET", "POST", "HEAD", "OPTIONS"}


class RagflowClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = str(settings.ragflow_base_url).rstrip("/")
        self.api_v1_url = f"{self.base_url}/api/v1"
        self._client = httpx.AsyncClient(
            timeout=float(settings.request_timeout_seconds),
            headers={
                "Authorization": f"Bearer {settings.ragflow_api_key}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def probe_healthz(self) -> Tuple[bool, Optional[str]]:
        try:
            response = await self._client.get(f"{self.base_url}/v1/system/healthz")
            if response.is_success:
                return True, None
        except httpx.TimeoutException:
            return False, "RAGFlow health probe timed out."
        except httpx.HTTPError as exc:
            return False, f"RAGFlow health probe failed: {exc}"
        return False, f"RAGFlow health probe returned status {response.status_code}."

    async def list_datasets(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            data = await self._request_json(
                "GET",
                f"{self.api_v1_url}/datasets",
                params={"page": page, "page_size": page_size},
            )
            page_items = self._as_list(data)
            items.extend(page_items)
            if len(page_items) < page_size:
                break
            page += 1
        return items

    async def list_documents(self, dataset_id: str, *, page_size: int) -> tuple[list[dict[str, Any]], int]:
        data = await self._request_json(
            "GET",
            f"{self.api_v1_url}/datasets/{dataset_id}/documents",
            params={"page": 1, "page_size": page_size, "orderby": "update_time", "desc": True},
        )
        documents = self._as_list(data)
        total = len(documents)
        if isinstance(data, dict) and isinstance(data.get("total"), int):
            total = int(data["total"])
        return documents, total

    async def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request_json("POST", f"{self.api_v1_url}/retrieval", json=payload)
        return data if isinstance(data, dict) else {"chunks": self._as_list(data), "total": len(self._as_list(data))}

    async def download_document(self, dataset_id: str, document_id: str) -> tuple[bytes, dict[str, str]]:
        response = await self._request_raw("GET", f"{self.api_v1_url}/datasets/{dataset_id}/documents/{document_id}")
        headers = {
            "content-type": response.headers.get("content-type", "application/octet-stream"),
            "content-disposition": response.headers.get("content-disposition", ""),
        }
        return response.content, headers

    async def _request_raw(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempts = 0
        while True:
            attempts += 1
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                raise api_error(
                    status_code=504,
                    code="ragflow_timeout",
                    message="RAGFlow request timed out.",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                raise api_error(
                    status_code=502,
                    code="ragflow_network_error",
                    message=f"Failed to reach RAGFlow: {exc}",
                    retryable=True,
                ) from exc
            if method.upper() in RETRYABLE_METHODS and response.status_code in {429, 500, 502, 503, 504} and attempts < 4:
                await asyncio.sleep(0.3 * (2 ** (attempts - 1)))
                continue
            self._raise_for_status(response)
            return response

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        response = await self._request_raw(method, url, **kwargs)
        if response.status_code == 204:
            return None
        body = response.json()
        if isinstance(body, dict) and "code" in body:
            if body.get("code") != 0:
                message = str(body.get("message") or "RAGFlow returned an error.")
                raise api_error(status_code=502, code="ragflow_api_error", message=message)
            return body.get("data")
        return body

    def _raise_for_status(self, response: httpx.Response) -> None:
        if not response.is_error:
            return
        logger.warning("RAGFlow API error status=%s url=%s", response.status_code, response.request.url)
        if response.status_code in {401, 403}:
            raise api_error(
                status_code=502,
                code="ragflow_auth_failed",
                message="RAGFlow rejected the API key or permissions.",
            )
        if response.status_code == 404:
            raise api_error(status_code=502, code="ragflow_not_found", message="RAGFlow resource was not found.")
        if response.status_code in {429, 500, 502, 503, 504}:
            raise api_error(
                status_code=502,
                code="ragflow_upstream_error",
                message=f"RAGFlow returned upstream status {response.status_code}.",
                retryable=True,
            )
        message = response.text
        try:
            body = response.json()
            if isinstance(body, dict):
                message = str(body.get("message") or body.get("detail") or message)
        except Exception:
            pass
        raise api_error(status_code=502, code="ragflow_api_error", message=message)

    def _as_list(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("docs", "documents", "chunks", "results"):
                raw = data.get(key)
                if isinstance(raw, list):
                    return [item for item in raw if isinstance(item, dict)]
        return []
