from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_json(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read().decode("utf-8")
            return response.status, content
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send mock webhook lead events to local API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--channel", choices=["whatsapp", "telephony"], default="whatsapp")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--secret", default="")
    args = parser.parse_args()

    endpoint = f"{args.base_url.rstrip('/')}/webhooks/{args.channel}"
    for index in range(args.start_index, args.start_index + args.count):
        event_id = f"evt_mock_{args.channel}_{index}"
        phone = f"90000{index:05d}"[-10:]
        payload = {
            "event_id": event_id,
            "event_type": args.event_type
            or ("candidate_lead" if args.channel == "whatsapp" else "call_lead"),
            "phone": phone,
            "payload": {
                "name": f"Fresher Therapist {index}",
                "phone": phone,
                "languages": ["kn", "en"],
                "therapy_experience": [],
                "experience_years": 0,
                "certifications": [],
                "job_id": args.job_id,
                "notes": "mock lead generated locally",
            },
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers: dict[str, str] = {}
        if args.secret:
            signed = sign_payload(args.secret, body)
            if args.channel == "whatsapp":
                headers["X-Hub-Signature-256"] = signed
            else:
                headers["X-Telephony-Signature"] = signed
        status_code, response = post_json(endpoint, body, headers)
        print(f"{status_code} {event_id} {response}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
