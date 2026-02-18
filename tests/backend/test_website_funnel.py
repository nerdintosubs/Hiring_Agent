from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.models import utc_now
from backend.app.services.recaptcha import (
    RecaptchaVerificationError,
    RecaptchaVerificationResult,
)


def test_create_website_lead_uses_default_sla_and_wa_link(client) -> None:
    response = client.post(
        "/leads/website",
        json={
            "name": "Website Candidate",
            "phone": "9000011111",
            "languages": ["kn", "en"],
            "utm_source": "google",
            "landing_path": "/careers/therapist",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["lead_id"].startswith("wlead_")
    assert data["candidate_id"].startswith("cand_")
    assert data["first_contact_sla_minutes_effective"] == 30
    assert "https://wa.me/919187351205?text=" in data["wa_link"]

    due = datetime.fromisoformat(data["first_contact_due_utc"])
    delta = due - datetime.utcnow()
    assert timedelta(minutes=29) <= delta <= timedelta(minutes=31)


def test_campaign_override_changes_sla_and_whatsapp_number(client) -> None:
    bootstrap = client.post(
        "/campaigns/first-10/bootstrap",
        json={
            "employer_name": "Website Campaign Spa",
            "neighborhood_focus": ["HSR"],
            "whatsapp_business_number": "+918888777666",
            "target_joiners": 10,
            "fresher_preferred": True,
            "first_contact_sla_minutes": 15,
        },
    )
    assert bootstrap.status_code == 200
    campaign_id = bootstrap.json()["campaign_id"]
    assert bootstrap.json()["first_contact_sla_minutes_effective"] == 15

    response = client.post(
        "/leads/website",
        json={
            "name": "Campaign Candidate",
            "phone": "9000012222",
            "campaign_id": campaign_id,
            "utm_source": "instagram",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["first_contact_sla_minutes_effective"] == 15
    assert "https://wa.me/918888777666?text=" in data["wa_link"]


def test_website_events_update_wa_click_and_summary(client) -> None:
    create = client.post(
        "/leads/website",
        json={
            "name": "Event Candidate",
            "phone": "9000013333",
            "utm_source": "meta_ads",
            "neighborhood": "HSR",
        },
    )
    assert create.status_code == 200
    lead_id = create.json()["lead_id"]

    form_event = client.post(
        "/events/website",
        json={
            "event_type": "form_submit",
            "lead_id": lead_id,
            "utm_source": "meta_ads",
        },
    )
    assert form_event.status_code == 200

    wa_event = client.post(
        "/events/website",
        json={
            "event_type": "wa_click",
            "lead_id": lead_id,
            "utm_source": "meta_ads",
        },
    )
    assert wa_event.status_code == 200

    leads = client.get("/leads/website?queue_mode=hot_new&limit=10")
    assert leads.status_code == 200
    items = leads.json()
    matching = [item for item in items if item["lead_id"] == lead_id]
    assert matching
    assert matching[0]["wa_click_count"] == 1

    summary = client.get("/funnel/website/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["event_counts"]["form_submit"] >= 1
    assert data["event_counts"]["wa_click"] >= 1
    assert data["total_leads"] >= 1
    assert data["leads_by_source"]["meta_ads"] >= 1
    assert data["leads_by_neighborhood"]["hsr"] >= 1


def test_overdue_queue_and_contact_update_marks_sla_breach(client) -> None:
    create = client.post(
        "/leads/website",
        json={
            "name": "Overdue Candidate",
            "phone": "9000014444",
        },
    )
    assert create.status_code == 200
    lead_id = create.json()["lead_id"]

    store = client.app.state.store
    with store._lock:
        record = store.website_leads[lead_id]
        store.website_leads[lead_id] = record.model_copy(
            update={
                "first_contact_due_utc": utc_now() - timedelta(minutes=1),
                "updated_at_utc": utc_now(),
            }
        )

    overdue = client.get("/leads/website?queue_mode=overdue")
    assert overdue.status_code == 200
    assert any(item["lead_id"] == lead_id for item in overdue.json())

    mark_contact = client.post(f"/leads/website/{lead_id}/contact")
    assert mark_contact.status_code == 200
    assert mark_contact.json()["sla_breached"] is True

    overdue_after = client.get("/leads/website?queue_mode=overdue")
    assert overdue_after.status_code == 200
    assert all(item["lead_id"] != lead_id for item in overdue_after.json())


def test_website_summary_rejects_invalid_date_range(client) -> None:
    response = client.get("/funnel/website/summary?date_from=2026-03-01&date_to=2026-02-01")
    assert response.status_code == 400


def test_recap_enabled_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RECAPTCHA_ENABLED", "true")
    monkeypatch.setenv("RECAPTCHA_SECRET", "test-secret")
    client = TestClient(create_app())

    response = client.post(
        "/leads/website",
        json={"name": "Recaptcha Candidate", "phone": "9000050000"},
    )
    assert response.status_code == 400
    assert "missing recaptcha token" in response.text


def test_recap_enabled_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RECAPTCHA_ENABLED", "true")
    monkeypatch.setenv("RECAPTCHA_SECRET", "test-secret")

    def fake_verify(**_kwargs):
        raise RecaptchaVerificationError("recaptcha token rejected")

    monkeypatch.setattr("backend.app.main.verify_recaptcha_token", fake_verify)
    client = TestClient(create_app())
    response = client.post(
        "/leads/website",
        json={
            "name": "Recaptcha Candidate",
            "phone": "9000050001",
            "recaptcha_token": "bad-token",
        },
    )
    assert response.status_code == 403
    assert "recaptcha token rejected" in response.text


def test_recap_enabled_accepts_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RECAPTCHA_ENABLED", "true")
    monkeypatch.setenv("RECAPTCHA_SECRET", "test-secret")

    def fake_verify(**_kwargs):
        return RecaptchaVerificationResult(
            success=True,
            score=0.9,
            action="therapist_apply",
            hostname="bangaloredoorstepmassage.online",
        )

    monkeypatch.setattr("backend.app.main.verify_recaptcha_token", fake_verify)
    client = TestClient(create_app())
    response = client.post(
        "/leads/website",
        json={
            "name": "Recaptcha Candidate",
            "phone": "9000050002",
            "recaptcha_token": "ok-token",
        },
    )
    assert response.status_code == 200
    assert response.json()["lead_id"].startswith("wlead_")
