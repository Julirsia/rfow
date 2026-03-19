from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException


def api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    candidates: Optional[list[str]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> HTTPException:
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if candidates:
        detail["candidates"] = candidates
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)
