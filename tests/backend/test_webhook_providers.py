from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _signature(secret: str, payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_whatsapp_signature_required_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "topsecret")
    client = TestClient(create_app())
    payload = {
        "event_id": "evt_signature_1",
        "event_type": "candidate_lead",
        "payload": {"name": "Pooja", "phone": "9000011111"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 403


def test_whatsapp_signature_valid_processes_event(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    secret = "topsecret"
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", secret)
    client = TestClient(create_app())
    payload = {
        "event_id": "evt_signature_2",
        "event_type": "candidate_lead",
        "payload": {"name": "Nisha", "phone": "9000011112", "languages": ["kn", "en"]},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _signature(secret, payload)

    response = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": signature,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["attempts"] == 1
    assert "candidate_upserted" in data["detail"]


def test_telephony_transient_failures_retry_then_fail(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("TELEPHONY_WEBHOOK_SECRET", "")
    monkeypatch.setenv("WEBHOOK_MAX_RETRIES", "3")
    monkeypatch.setenv("WEBHOOK_RETRY_BACKOFF_SECONDS", "1")
    client = TestClient(create_app())
    payload = {
        "event_id": "evt_retry_1",
        "event_type": "call_lead",
        "payload": {"simulate_transient_error": True},
    }

    first = client.post("/webhooks/telephony", json=payload)
    second = client.post("/webhooks/telephony", json=payload)
    third = client.post("/webhooks/telephony", json=payload)
    fourth = client.post("/webhooks/telephony", json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "retry_pending"
    assert first.json()["attempts"] == 1

    assert second.status_code == 200
    assert second.json()["status"] == "retry_pending"
    assert second.json()["attempts"] == 2

    assert third.status_code == 200
    assert third.json()["status"] == "failed"
    assert third.json()["attempts"] == 3

    assert fourth.status_code == 200
    assert fourth.json()["status"] == "failed"
    assert fourth.json()["attempts"] == 3


def test_invalid_candidate_payload_is_tracked_as_failure(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "")
    client = TestClient(create_app())
    payload = {
        "event_id": "evt_invalid_payload_1",
        "event_type": "candidate_lead",
        "payload": {
            "name": "Ritu",
            "phone": "9000011122",
            "therapy_experience": None,
        },
    }

    response = client.post("/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["attempts"] == 1
    assert "invalid candidate lead payload" in data["detail"]


def test_referral_lead_source_attribution(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "")
    client = TestClient(create_app())
    intake = client.post(
        "/employers/intake",
        json={
            "employer_name": "Referral Test Spa",
            "contact_phone": "9999988888",
            "role": "Spa Therapist",
            "required_therapies": ["swedish"],
            "shift_start": "10:00",
            "shift_end": "19:00",
            "pay_min": 22000,
            "pay_max": 30000,
            "location_name": "BTM",
            "location": {"lat": 12.9166, "lon": 77.6101},
            "languages": ["kn", "en"],
            "urgency_hours": 48,
        },
    )
    assert intake.status_code == 200
    job_id = intake.json()["job_id"]

    response = client.post(
        "/webhooks/whatsapp",
        json={
            "event_id": "evt_referral_1",
            "event_type": "referral_lead",
            "payload": {
                "name": "Sneha",
                "phone": "9000011133",
                "job_id": job_id,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    pipeline = client.get(f"/jobs/{job_id}/pipeline")
    assert pipeline.status_code == 200
    apps = pipeline.json()["applications"]
    assert len(apps) == 1
    assert apps[0]["source_channel"] == "referral"
