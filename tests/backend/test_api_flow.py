from __future__ import annotations

from datetime import datetime, timedelta


def build_intake_payload() -> dict:
    return {
        "employer_name": "HSR Wellness Center",
        "contact_phone": "9999988888",
        "role": "Spa Therapist",
        "required_therapies": ["deep tissue", "swedish"],
        "shift_start": "10:00",
        "shift_end": "19:00",
        "pay_min": 22000,
        "pay_max": 32000,
        "location_name": "HSR Layout",
        "location": {"lat": 12.9116, "lon": 77.6474},
        "languages": ["kn", "en", "hi"],
        "urgency_hours": 48,
    }


def build_candidate_payload(job_id: str) -> dict:
    return {
        "name": "Kiran M",
        "phone": "9000011111",
        "source_channel": "referral",
        "languages": ["kn", "en"],
        "therapy_experience": ["deep tissue", "swedish"],
        "experience_years": 3,
        "certifications": ["Ayurveda Foundation"],
        "expected_pay": 28000,
        "current_location": {"lat": 12.912, "lon": 77.64},
        "preferred_shift_start": "10:00",
        "preferred_shift_end": "19:00",
        "job_id": job_id,
    }


def test_pay_band_validation(client) -> None:
    payload = build_intake_payload()
    payload["pay_min"] = 40000
    payload["pay_max"] = 20000
    response = client.post("/employers/intake", json=payload)
    assert response.status_code == 422


def test_candidate_dedup_by_phone(client) -> None:
    intake = client.post("/employers/intake", json=build_intake_payload())
    assert intake.status_code == 200
    job_id = intake.json()["job_id"]

    first = client.post("/candidates/ingest", json=build_candidate_payload(job_id))
    assert first.status_code == 200
    first_json = first.json()
    assert first_json["deduplicated"] is False

    duplicate_payload = build_candidate_payload(job_id)
    duplicate_payload["name"] = "Kiran Manjunath"
    second = client.post("/candidates/ingest", json=duplicate_payload)
    assert second.status_code == 200
    second_json = second.json()
    assert second_json["deduplicated"] is True
    assert second_json["candidate_id"] == first_json["candidate_id"]


def test_invalid_stage_transition_is_blocked(client) -> None:
    intake = client.post("/employers/intake", json=build_intake_payload())
    job_id = intake.json()["job_id"]
    candidate = client.post("/candidates/ingest", json=build_candidate_payload(job_id)).json()
    application_id = candidate["application_id"]

    transition = client.post(
        f"/applications/{application_id}/stage",
        json={"to_stage": "offered", "reason": "manual_override"},
    )
    assert transition.status_code == 409


def test_end_to_end_pipeline(client) -> None:
    intake = client.post("/employers/intake", json=build_intake_payload()).json()
    job_id = intake["job_id"]
    candidate = client.post("/candidates/ingest", json=build_candidate_payload(job_id)).json()
    candidate_id = candidate["candidate_id"]
    application_id = candidate["application_id"]

    screening = client.post(
        "/screening/run",
        json={"job_id": job_id, "candidate_id": candidate_id},
    )
    assert screening.status_code == 200
    assert screening.json()["hard_filter_pass"] is True

    interview_time = datetime.utcnow() + timedelta(days=1)
    interview = client.post(
        "/interviews/schedule",
        json={
            "job_id": job_id,
            "candidate_id": candidate_id,
            "mode": "phone",
            "scheduled_at_utc": interview_time.isoformat(),
        },
    )
    assert interview.status_code == 200

    shortlist = client.post("/shortlist/generate", json={"job_id": job_id, "top_k": 1})
    assert shortlist.status_code == 200
    shortlisted = shortlist.json()["shortlisted"]
    assert len(shortlisted) == 1

    offer = client.post(
        "/offers/create",
        json={
            "application_id": application_id,
            "monthly_pay": 30000,
            "joining_date": "2026-03-01",
        },
    )
    assert offer.status_code == 200
    assert offer.json()["status"] == "pending_acceptance"

    pipeline = client.get(f"/jobs/{job_id}/pipeline")
    assert pipeline.status_code == 200
    counts = pipeline.json()["counts"]
    assert counts["offered"] == 1


def test_webhook_idempotency(client) -> None:
    payload = {"event_id": "evt_001", "event_type": "message", "payload": {"text": "hi"}}
    first = client.post("/webhooks/whatsapp", json=payload)
    second = client.post("/webhooks/whatsapp", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"

