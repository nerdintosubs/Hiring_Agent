from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(
    *, url: str, token: str | None = None
) -> tuple[int, dict | None, str]:
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body) if body.startswith("{") or body.startswith("[") else None
            return response.status, data, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        return exc.code, data, body


def request_text(*, url: str, token: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for Hiring Agent API.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--auth-mode", choices=["enabled", "disabled"], default="enabled")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    token = args.token.strip() or None

    status, data, _ = request_json(url=f"{base_url}/health")
    assert_true(status == 200, f"/health expected 200, got {status}")
    assert_true(isinstance(data, dict) and data.get("status") == "ok", "/health invalid payload")
    print("OK /health")

    status, data, _ = request_json(url=f"{base_url}/health/ready")
    assert_true(status == 200, f"/health/ready expected 200, got {status}")
    assert_true(
        isinstance(data, dict) and data.get("status") == "ready",
        "/health/ready invalid payload",
    )
    print("OK /health/ready")

    status, body = request_text(url=f"{base_url}/metrics")
    assert_true(status == 200, f"/metrics expected 200, got {status}")
    assert_true("hiring_agent_requests_total" in body, "/metrics missing requests counter")
    print("OK /metrics")

    protected_status, _, _ = request_json(url=f"{base_url}/leads/manual?limit=1", token=token)
    if args.auth_mode == "enabled":
        if token:
            assert_true(
                protected_status == 200,
                f"/leads/manual with token expected 200, got {protected_status}",
            )
            print("OK /leads/manual with token")
        else:
            assert_true(
                protected_status in {401, 403},
                f"/leads/manual without token expected 401/403, got {protected_status}",
            )
            print("OK /leads/manual unauthorized")
    else:
        assert_true(
            protected_status == 200,
            f"/leads/manual expected 200 with auth disabled, got {protected_status}",
        )
        print("OK /leads/manual with auth disabled")

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        sys.exit(1)

