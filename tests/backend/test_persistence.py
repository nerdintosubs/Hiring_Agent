from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.persistence import SqlitePersistence


def _new_client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "true")
    monkeypatch.setenv("PERSISTENCE_DB_PATH", str(db_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{str(db_path).replace(chr(92), '/')}")
    monkeypatch.setenv("TELEPHONY_WEBHOOK_SECRET", "")
    monkeypatch.setenv("WEBHOOK_MAX_RETRIES", "3")
    monkeypatch.setenv("WEBHOOK_RETRY_BACKOFF_SECONDS", "1")
    return TestClient(create_app())


def test_webhook_attempts_persist_across_restart(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "hiring_agent.sqlite3"
    payload = {
        "event_id": "evt_persist_retry_1",
        "event_type": "call_lead",
        "payload": {"simulate_transient_error": True},
    }

    first_client = _new_client(monkeypatch, db_path)
    first = first_client.post("/webhooks/telephony", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "retry_pending"
    assert first.json()["attempts"] == 1

    restarted_client = _new_client(monkeypatch, db_path)
    second = restarted_client.post("/webhooks/telephony", json=payload)
    assert second.status_code == 200
    assert second.json()["status"] == "retry_pending"
    assert second.json()["attempts"] == 2


def test_manual_leads_persist_across_restart(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "hiring_agent.sqlite3"
    first_client = _new_client(monkeypatch, db_path)
    create = first_client.post(
        "/leads/manual",
        json={
            "source_channel": "walk_in",
            "name": "Shruti",
            "phone": "9000019999",
            "languages": ["kn"],
            "notes": "persist test",
        },
    )
    assert create.status_code == 200
    lead_id = create.json()["lead_id"]

    restarted_client = _new_client(monkeypatch, db_path)
    listed = restarted_client.get("/leads/manual?limit=20")
    assert listed.status_code == 200
    ids = [item["lead_id"] for item in listed.json()]
    assert lead_id in ids


def test_sqlite_url_creates_missing_parent_directories(tmp_path) -> None:
    db_path = tmp_path / "nested" / "hiring_agent.sqlite3"
    persistence = SqlitePersistence(f"sqlite:///{db_path.as_posix()}")
    assert db_path.parent.exists()
    assert persistence.ping()
