from __future__ import annotations

from datetime import datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from backend.app.main import create_app


def _token(secret: str, subject: str, roles: list[str]) -> str:
    payload = {
        "sub": subject,
        "roles": roles,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_auth_blocks_missing_token_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = TestClient(create_app())

    response = client.post(
        "/employers/intake",
        json={
            "employer_name": "Auth Test",
            "contact_phone": "9999988888",
            "role": "Spa Therapist",
            "required_therapies": [],
            "shift_start": "10:00",
            "shift_end": "19:00",
            "pay_min": 22000,
            "pay_max": 30000,
            "location_name": "HSR",
            "location": {"lat": 12.91, "lon": 77.64},
            "languages": ["kn"],
            "urgency_hours": 48,
        },
    )
    assert response.status_code == 401


def test_auth_allows_recruiter_token(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = TestClient(create_app())
    token = _token("test-secret", "recruiter-1", ["recruiter"])

    response = client.post(
        "/employers/intake",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employer_name": "Auth Test",
            "contact_phone": "9999988888",
            "role": "Spa Therapist",
            "required_therapies": [],
            "shift_start": "10:00",
            "shift_end": "19:00",
            "pay_min": 22000,
            "pay_max": 30000,
            "location_name": "HSR",
            "location": {"lat": 12.91, "lon": 77.64},
            "languages": ["kn"],
            "urgency_hours": 48,
        },
    )
    assert response.status_code == 200


def test_website_lead_ingest_is_public_even_when_auth_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = TestClient(create_app())

    response = client.post(
        "/leads/website",
        json={
            "name": "Public Website Lead",
            "phone": "9000088888",
            "utm_source": "site_form",
        },
    )
    assert response.status_code == 200
