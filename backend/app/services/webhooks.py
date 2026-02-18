from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from starlette.datastructures import Headers


class SignatureVerificationError(Exception):
    pass


def _header_value(headers: Headers, candidates: list[str]) -> Optional[str]:
    for key in candidates:
        value = headers.get(key)
        if value:
            return value.strip()
    return None


def _verify_hmac_sha256(raw_body: bytes, secret: str, incoming_signature: str) -> bool:
    provided = incoming_signature.strip()
    if provided.startswith("sha256="):
        provided = provided.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def verify_whatsapp_signature(headers: Headers, raw_body: bytes, secret: str) -> None:
    if not secret:
        return
    signature = _header_value(
        headers,
        ["x-hub-signature-256", "x-whatsapp-signature-256", "x-webhook-signature"],
    )
    if not signature:
        raise SignatureVerificationError("missing whatsapp signature header")
    if not _verify_hmac_sha256(raw_body, secret, signature):
        raise SignatureVerificationError("invalid whatsapp signature")


def verify_telephony_signature(headers: Headers, raw_body: bytes, secret: str) -> None:
    if not secret:
        return
    signature = _header_value(
        headers,
        ["x-telephony-signature", "x-provider-signature", "x-webhook-signature"],
    )
    if not signature:
        raise SignatureVerificationError("missing telephony signature header")
    if not _verify_hmac_sha256(raw_body, secret, signature):
        raise SignatureVerificationError("invalid telephony signature")

