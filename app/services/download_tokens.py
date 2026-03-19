from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from app.errors import api_error
from app.models.common import SourceDownloadRef


class DownloadTokenSigner:
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def sign(self, *, dataset_id: str, document_id: str, filename: str) -> str:
        exp = int((datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).timestamp())
        payload = {
            "dataset_id": dataset_id,
            "document_id": document_id,
            "filename": filename,
            "exp": exp,
        }
        return self._encode(payload)

    def verify(self, token: str) -> SourceDownloadRef:
        payload = self._decode(token)
        try:
            data = SourceDownloadRef.model_validate(payload)
        except Exception as exc:
            raise api_error(status_code=400, code="invalid_download_token", message="Invalid download token.") from exc
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if data.exp < now_ts:
            raise api_error(status_code=410, code="download_token_expired", message="Download token has expired.")
        return data

    def _encode(self, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.secret, raw, hashlib.sha256).hexdigest().encode("ascii")
        packed = base64.urlsafe_b64encode(raw + b"." + signature)
        return packed.decode("ascii").rstrip("=")

    def _decode(self, token: str) -> dict[str, object]:
        padded = token + "=" * ((4 - len(token) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            raw, provided_sig = decoded.rsplit(b".", 1)
        except Exception as exc:
            raise api_error(status_code=400, code="invalid_download_token", message="Invalid download token.") from exc
        expected_sig = hmac.new(self.secret, raw, hashlib.sha256).hexdigest().encode("ascii")
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise api_error(status_code=400, code="invalid_download_token", message="Invalid download token.")
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise api_error(status_code=400, code="invalid_download_token", message="Invalid download token.") from exc
