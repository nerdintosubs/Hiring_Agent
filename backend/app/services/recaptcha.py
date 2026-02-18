from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib import parse, request
from urllib.error import URLError


class RecaptchaServiceError(Exception):
    pass


class RecaptchaVerificationError(Exception):
    pass


@dataclass(frozen=True)
class RecaptchaVerificationResult:
    success: bool
    score: float
    action: Optional[str]
    hostname: Optional[str]


def verify_recaptcha_token(
    *,
    token: str,
    secret: str,
    min_score: float,
    remote_ip: Optional[str] = None,
    expected_action: Optional[str] = None,
) -> RecaptchaVerificationResult:
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    encoded = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        "https://www.google.com/recaptcha/api/siteverify",
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8")
    except URLError as exc:
        raise RecaptchaServiceError("recaptcha verification request failed") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RecaptchaServiceError("recaptcha verification response was not valid json") from exc

    success = bool(decoded.get("success"))
    score = float(decoded.get("score", 0.0) or 0.0)
    action = decoded.get("action")
    hostname = decoded.get("hostname")

    if not success:
        raise RecaptchaVerificationError("recaptcha token rejected")
    if score < min_score:
        raise RecaptchaVerificationError("recaptcha score below threshold")
    if expected_action and action and action != expected_action:
        raise RecaptchaVerificationError("recaptcha action mismatch")

    return RecaptchaVerificationResult(
        success=success,
        score=score,
        action=action,
        hostname=hostname,
    )
