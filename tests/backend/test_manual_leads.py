from __future__ import annotations

from datetime import timedelta

from backend.app.models import utc_now


def test_manual_lead_create_with_job_generates_application(client) -> None:
    intake_response = client.post(
        "/employers/intake",
        json={
            "employer_name": "HSR Therapy Hub",
            "contact_phone": "9999988888",
            "role": "Spa Therapist",
            "required_therapies": ["deep tissue"],
            "shift_start": "10:00",
            "shift_end": "19:00",
            "pay_min": 22000,
            "pay_max": 30000,
            "location_name": "HSR Layout",
            "location": {"lat": 12.9116, "lon": 77.6474},
            "languages": ["kn", "en"],
            "urgency_hours": 48,
        },
    )
    assert intake_response.status_code == 200
    job_id = intake_response.json()["job_id"]

    lead_response = client.post(
        "/leads/manual",
        json={
            "source_channel": "walk_in",
            "name": "Aishwarya",
            "phone": "9000012312",
            "languages": ["kn", "en"],
            "therapy_experience": [],
            "experience_years": 0,
            "job_id": job_id,
            "neighborhood": "HSR Layout",
            "notes": "fresher from local referral",
            "created_by": "recruiter_1",
        },
    )
    assert lead_response.status_code == 200
    lead_data = lead_response.json()
    assert lead_data["lead_id"].startswith("lead_")
    assert lead_data["candidate_id"].startswith("cand_")
    assert lead_data["application_id"].startswith("app_")

    list_response = client.get("/leads/manual?limit=10")
    assert list_response.status_code == 200
    leads = list_response.json()
    assert len(leads) >= 1
    assert leads[0]["lead_id"] == lead_data["lead_id"]


def test_manual_lead_missing_job_returns_404(client) -> None:
    response = client.post(
        "/leads/manual",
        json={
            "source_channel": "walk_in",
            "name": "Nandini",
            "phone": "9000012399",
            "job_id": "job_missing",
        },
    )
    assert response.status_code == 404


def test_manual_lead_filters(client) -> None:
    base_payload = {
        "name": "Asha",
        "phone": "9000010001",
        "source_channel": "walk_in",
        "neighborhood": "HSR Layout",
        "created_by": "recruiter_a",
        "notes": "fresh walk-in",
    }
    first = client.post("/leads/manual", json=base_payload)
    assert first.status_code == 200

    second_payload = dict(base_payload)
    second_payload.update(
        {
            "name": "Divya",
            "phone": "9000010002",
            "source_channel": "referral",
            "neighborhood": "Indiranagar",
            "created_by": "recruiter_b",
            "notes": "institute referral",
        }
    )
    second = client.post("/leads/manual", json=second_payload)
    assert second.status_code == 200

    by_source = client.get("/leads/manual?source_channel=walk_in")
    assert by_source.status_code == 200
    assert len(by_source.json()) == 1
    assert by_source.json()[0]["source_channel"] == "walk_in"

    by_neighborhood = client.get("/leads/manual?neighborhood=indira")
    assert by_neighborhood.status_code == 200
    assert len(by_neighborhood.json()) == 1
    assert by_neighborhood.json()[0]["name"] == "Divya"

    by_recruiter = client.get("/leads/manual?created_by=recruiter_a")
    assert by_recruiter.status_code == 200
    assert len(by_recruiter.json()) == 1
    assert by_recruiter.json()[0]["name"] == "Asha"

    by_search = client.get("/leads/manual?search=institute")
    assert by_search.status_code == 200
    assert len(by_search.json()) == 1
    assert by_search.json()[0]["name"] == "Divya"

    today = utc_now().date().isoformat()
    future = (utc_now().date() + timedelta(days=1)).isoformat()
    by_date = client.get(f"/leads/manual?created_from={today}&created_to={future}")
    assert by_date.status_code == 200
    assert len(by_date.json()) >= 2
