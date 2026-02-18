from __future__ import annotations


def test_bootstrap_first_ten_campaign_returns_templates(client) -> None:
    response = client.post(
        "/campaigns/first-10/bootstrap",
        json={
            "employer_name": "Koramangala Wellness Spa",
            "neighborhood_focus": ["Koramangala", "HSR Layout", "BTM"],
            "whatsapp_business_number": "+919187351205",
            "target_joiners": 10,
            "fresher_preferred": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Bangalore"
    assert data["target_funnel"]["joined"] == 10
    assert "+919187351205" in data["templates"]["whatsapp_job_post"]
    assert data["campaign_id"].startswith("cmp_")


def test_campaign_progress_updates_after_events(client) -> None:
    bootstrap = client.post(
        "/campaigns/first-10/bootstrap",
        json={
            "employer_name": "Indiranagar Therapy Center",
            "neighborhood_focus": ["Indiranagar"],
            "whatsapp_business_number": "+919187351205",
            "target_joiners": 10,
            "fresher_preferred": True,
        },
    ).json()
    campaign_id = bootstrap["campaign_id"]

    events = [
        ("leads", 120),
        ("screened", 60),
        ("trials", 30),
        ("offers", 15),
        ("joined", 10),
    ]
    for event_type, count in events:
        response = client.post(
            f"/campaigns/{campaign_id}/events",
            json={"event_type": event_type, "count": count},
        )
        assert response.status_code == 200

    progress = client.get(f"/campaigns/{campaign_id}/progress")
    assert progress.status_code == 200
    data = progress.json()
    assert data["counts"]["joined"] == 10
    assert data["health_status"] == "on_track"
    assert data["conversion_rates"]["offer_to_joined"] >= 60.0


def test_campaign_not_found_returns_404(client) -> None:
    response = client.get("/campaigns/cmp_missing/progress")
    assert response.status_code == 404

