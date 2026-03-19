from __future__ import annotations

from typing import Literal, Optional

from app.models.common import FlatResponseModel


class HealthResponse(FlatResponseModel):
    ok: bool
    wrapper_status: Literal["ok", "degraded"]
    ragflow_status: Literal["ok", "degraded", "unreachable"]
    ragflow_probe: str
    ragflow_error: Optional[str] = None
