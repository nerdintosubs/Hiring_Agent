from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

import jwt

AREAS = [
    "hsr",
    "btm",
    "koramangala",
    "jp nagar",
    "electronic city",
    "marathahalli",
    "indiranagar",
    "whitefield",
    "jayanagar",
    "rajajinagar",
    "hebbal",
    "yelahanka",
    "banashankari",
    "bellandur",
    "sarjapur",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 10:
        return digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return ""


def parse_seeds(raw: str) -> list[str]:
    values = [item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def infer_languages(text: str) -> list[str]:
    value = (text or "").lower()
    langs: list[str] = []
    if any(token in value for token in ["kannada", "kannadiga", "ಬೆಂಗಳೂರು", "bengaluru"]):
        langs.append("kn")
    if any(token in value for token in ["hindi", "hind", "हिंदी"]):
        langs.append("hi")
    if any(token in value for token in ["tamil", "தமிழ்"]):
        langs.append("ta")
    if any(token in value for token in ["telugu", "తెలుగు"]):
        langs.append("te")
    if "english" in value or not langs:
        langs.append("en")
    return sorted(set(langs))


def extract_neighborhood(text: str) -> str | None:
    value = (text or "").lower()
    for area in AREAS:
        if area in value:
            return area.upper() if len(area) <= 3 else area.title()
    return None


def locality_score(text: str) -> int:
    value = (text or "").lower()
    score = 0
    if any(token in value for token in ["bangalore", "bengaluru", "blr"]):
        score += 2
    score += sum(1 for area in AREAS if area in value)
    return score


def generate_dm_script(name: str, wa_number: str) -> str:
    first_name = (name or "").split(" ")[0].strip() or "there"
    return (
        f"Hi {first_name}, we are hiring female therapist fresher roles in Bangalore "
        f"(paid training + fixed salary + incentives). "
        f"Can we do a quick 5-min screening today? WhatsApp: {wa_number}"
    )


def http_json(
    *,
    method: str,
    url: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        parsed = {"detail": body}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            pass
        return exc.code, parsed


@dataclass
class IngestResult:
    handle: str
    status: str
    priority_score: int
    lead_id: str | None = None
    candidate_id: str | None = None
    deduplicated: bool | None = None
    error_detail: str | None = None


def plan_capture_sheet(*, seeds: list[str], per_seed: int, output_csv: Path) -> None:
    ensure_parent(output_csv)
    rows: list[dict[str, str]] = []
    for seed in seeds:
        for slot in range(1, per_seed + 1):
            rows.append(
                {
                    "seed_account": seed,
                    "capture_slot": str(slot),
                    "target_handle": "",
                    "display_name": "",
                    "bio": "",
                    "location": "",
                    "phone": "",
                    "notes": "",
                }
            )
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seed_account",
                "capture_slot",
                "target_handle",
                "display_name",
                "bio",
                "location",
                "phone",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def ingest_capture_sheet(
    *,
    input_csv: Path,
    output_csv: Path,
    api_base: str,
    recruiter_jwt: str,
    created_by: str,
    campaign_id: str | None,
    wa_number: str,
    dry_run: bool,
    max_rows: int,
    state_csv: Path,
) -> dict[str, int]:
    ensure_parent(output_csv)
    ensure_parent(state_csv)
    rows: list[dict[str, str]] = []
    processed_handles: set[str] = set()
    if state_csv.exists():
        with state_csv.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                handle = row.get("target_handle", "").strip().lower().lstrip("@")
                if handle:
                    processed_handles.add(handle)

    stats = {
        "processed": 0,
        "lead_created": 0,
        "needs_phone": 0,
        "errors": 0,
        "deduplicated": 0,
        "skipped_already_processed": 0,
    }
    with input_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if stats["processed"] >= max_rows:
                break
            handle = row.get("target_handle", "").strip().lstrip("@")
            if not handle:
                continue
            if handle.lower() in processed_handles:
                stats["skipped_already_processed"] += 1
                continue

            stats["processed"] += 1
            name = row.get("display_name", "").strip() or handle
            phone = normalize_phone(row.get("phone", ""))
            bio = row.get("bio", "").strip()
            location = row.get("location", "").strip()
            seed_account = row.get("seed_account", "").strip().lstrip("@")
            text_blob = f"{bio} {location}"
            languages = infer_languages(text_blob)
            neighborhood = extract_neighborhood(text_blob)
            priority = locality_score(text_blob) * 10 + (20 if phone else 0)

            bio_compact = re.sub(r"\s+", " ", bio)[:120]
            base_notes = (
                f"instagram_outreach|seed:@{seed_account}|handle:@{handle}|"
                f"location={location}|bio={bio_compact}"
            )

            ingest_result = IngestResult(
                handle=handle,
                status="needs_phone",
                priority_score=priority,
            )
            if phone:
                payload = {
                    "source_channel": "web",
                    "name": name,
                    "phone": phone,
                    "languages": languages,
                    "neighborhood": neighborhood,
                    "notes": base_notes,
                    "created_by": created_by,
                    "job_id": None,
                }
                if not dry_run:
                    status, response = http_json(
                        method="POST",
                        url=f"{api_base.rstrip('/')}/leads/manual",
                        token=recruiter_jwt,
                        payload=payload,
                    )
                    if status == 200:
                        ingest_result.status = "lead_created"
                        ingest_result.lead_id = response.get("lead_id")
                        ingest_result.candidate_id = response.get("candidate_id")
                        ingest_result.deduplicated = bool(response.get("deduplicated"))
                        stats["lead_created"] += 1
                        if ingest_result.deduplicated:
                            stats["deduplicated"] += 1
                        processed_handles.add(handle.lower())
                    else:
                        ingest_result.status = "error"
                        ingest_result.error_detail = str(response.get("detail", "unknown"))
                        stats["errors"] += 1
                else:
                    ingest_result.status = "lead_created_dry_run"
                    stats["lead_created"] += 1
                    processed_handles.add(handle.lower())
            else:
                stats["needs_phone"] += 1

            followup_1 = (utc_now() + timedelta(hours=24)).isoformat()
            followup_2 = (utc_now() + timedelta(hours=72)).isoformat()
            dm_script = generate_dm_script(name=name, wa_number=wa_number)
            rows.append(
                {
                    "seed_account": seed_account,
                    "target_handle": handle,
                    "display_name": name,
                    "phone": phone,
                    "campaign_id": campaign_id or "",
                    "status": ingest_result.status,
                    "priority_score": str(ingest_result.priority_score),
                    "lead_id": ingest_result.lead_id or "",
                    "candidate_id": ingest_result.candidate_id or "",
                    "deduplicated": str(bool(ingest_result.deduplicated)),
                    "languages": ",".join(languages),
                    "neighborhood": neighborhood or "",
                    "dm_script": dm_script,
                    "followup_1_utc": followup_1,
                    "followup_2_utc": followup_2,
                    "error_detail": ingest_result.error_detail or "",
                }
            )

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seed_account",
                "target_handle",
                "display_name",
                "phone",
                "campaign_id",
                "status",
                "priority_score",
                "lead_id",
                "candidate_id",
                "deduplicated",
                "languages",
                "neighborhood",
                "dm_script",
                "followup_1_utc",
                "followup_2_utc",
                "error_detail",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    with state_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_handle", "processed_at_utc"])
        writer.writeheader()
        now = utc_now().isoformat()
        for handle in sorted(processed_handles):
            writer.writerow({"target_handle": handle, "processed_at_utc": now})
    return stats


def recruiter_token_from_jwt_secret(
    *,
    jwt_secret: str,
    subject: str,
    roles: list[str],
    hours: int = 24,
) -> str:
    payload = {
        "sub": subject,
        "roles": roles,
        "exp": datetime.utcnow() + timedelta(hours=hours),
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    return str(token)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Automate daily Instagram therapist outreach ops without prohibited scraping. "
            "Mode=plan creates a capture sheet; mode=ingest converts captured rows into leads."
        )
    )
    parser.add_argument("--mode", choices=["plan", "ingest"], required=True)
    parser.add_argument("--seeds", default="refreshdspa,tiaradoorstep")
    parser.add_argument("--per-seed", type=int, default=50)
    parser.add_argument("--input-csv", default="data/instagram_capture_sheet.csv")
    parser.add_argument("--output-csv", default="")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--recruiter-jwt", default=os.getenv("RECRUITER_JWT", ""))
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET", ""))
    parser.add_argument("--jwt-subject", default=os.getenv("JWT_SUBJECT", "recruiter-automation"))
    parser.add_argument("--jwt-hours", type=int, default=24)
    parser.add_argument("--created-by", default="instagram-ops")
    parser.add_argument("--campaign-id", default="")
    parser.add_argument("--wa-number", default="+919187351205")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--state-csv", default="data/instagram_processed_handles.csv")
    args = parser.parse_args()

    today = utc_now().strftime("%Y%m%d")
    if args.output_csv:
        output_csv = Path(args.output_csv)
    elif args.mode == "plan":
        output_csv = Path(f"data/instagram_capture_sheet_{today}.csv")
    else:
        output_csv = Path(f"data/instagram_outreach_queue_{today}.csv")

    if args.mode == "plan":
        seeds = parse_seeds(args.seeds)
        if not seeds:
            raise SystemExit("No valid seed accounts provided.")
        plan_capture_sheet(seeds=seeds, per_seed=max(1, args.per_seed), output_csv=output_csv)
        print(f"Created capture sheet: {output_csv}")
        print(f"Seeds: {', '.join(seeds)} | Per seed: {max(1, args.per_seed)}")
        return 0

    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise SystemExit(f"Input CSV not found: {input_csv}")

    recruiter_jwt = args.recruiter_jwt
    if not recruiter_jwt and args.jwt_secret:
        recruiter_jwt = recruiter_token_from_jwt_secret(
            jwt_secret=args.jwt_secret,
            subject=args.jwt_subject,
            roles=["recruiter"],
            hours=max(1, args.jwt_hours),
        )
    if not recruiter_jwt and not args.dry_run:
        raise SystemExit(
            "Missing recruiter JWT. Set --recruiter-jwt, RECRUITER_JWT, "
            "or provide --jwt-secret/JWT_SECRET."
        )

    stats = ingest_capture_sheet(
        input_csv=input_csv,
        output_csv=output_csv,
        api_base=args.api_base,
        recruiter_jwt=recruiter_jwt,
        created_by=args.created_by,
        campaign_id=args.campaign_id or None,
        wa_number=args.wa_number,
        dry_run=args.dry_run,
        max_rows=max(1, args.max_rows),
        state_csv=Path(args.state_csv),
    )
    print(f"Created outreach queue: {output_csv}")
    print(
        "Stats: "
        f"processed={stats['processed']} "
        f"lead_created={stats['lead_created']} "
        f"needs_phone={stats['needs_phone']} "
        f"deduplicated={stats['deduplicated']} "
        f"skipped_already_processed={stats['skipped_already_processed']} "
        f"errors={stats['errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
