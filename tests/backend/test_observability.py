from __future__ import annotations


def test_metrics_endpoint_exposes_counters(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "hiring_agent_requests_total" in body
    assert "hiring_agent_requests_5xx_total" in body


def test_readiness_endpoint(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
