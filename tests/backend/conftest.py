from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    app = create_app()
    return TestClient(app)
