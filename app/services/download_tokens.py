from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from app.errors import api_error
from app.models.common import SourceDownloadRef, SourceSearchRef


class _SignedPayloadCodec:
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def _encode(self, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.secret, raw, hashlib.sha256).hexdigest().encode("ascii")
        packed = base64.urlsafe_b64encode(raw + b"." + signature)
        return packed.decode("ascii").rstrip("=")

    def _decode(self, token: str, *, invalid_code: str, invalid_message: str) -> dict[str, object]:
        padded = token + "=" * ((4 - len(token) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            raw, provided_sig = decoded.rsplit(b".", 1)
        except Exception as exc:
            raise api_error(status_code=400, code=invalid_code, message=invalid_message) from exc
        expected_sig = hmac.new(self.secret, raw, hashlib.sha256).hexdigest().encode("ascii")
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise api_error(status_code=400, code=invalid_code, message=invalid_message)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise api_error(status_code=400, code=invalid_code, message=invalid_message) from exc


class DownloadTokenSigner(_SignedPayloadCodec):
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        super().__init__(secret=secret, ttl_seconds=ttl_seconds)

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
        payload = self._decode(
            token,
            invalid_code="invalid_download_token",
            invalid_message="Invalid download token.",
        )
        try:
            data = SourceDownloadRef.model_validate(payload)
        except Exception as exc:
            raise api_error(status_code=400, code="invalid_download_token", message="Invalid download token.") from exc
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if data.exp < now_ts:
            raise api_error(status_code=410, code="download_token_expired", message="Download token has expired.")
        return data


class SourceRefSigner(_SignedPayloadCodec):
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        super().__init__(secret=secret, ttl_seconds=ttl_seconds)

    def sign(self, *, dataset_id: str, dataset_name: str, document_id: str, document_name: str) -> str:
        exp = int((datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).timestamp())
        payload = {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "document_id": document_id,
            "document_name": document_name,
            "exp": exp,
        }
        return self._encode(payload)

    def verify(self, token: str) -> SourceSearchRef:
        payload = self._decode(
            token,
            invalid_code="invalid_source_ref",
            invalid_message="Invalid source_ref.",
        )
        try:
            data = SourceSearchRef.model_validate(payload)
        except Exception as exc:
            raise api_error(status_code=400, code="invalid_source_ref", message="Invalid source_ref.") from exc
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if data.exp < now_ts:
            raise api_error(status_code=410, code="source_ref_expired", message="source_ref has expired.")
        return data
