from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from backend.app.models import CandidateIngestRequest, Language, SourceChannel, WebhookEventRequest
from backend.app.store import InMemoryStore, StoreNotFoundError


class TransientWebhookError(Exception):
    pass


class PermanentWebhookError(Exception):
    pass


def _parse_languages(values: object) -> list[Language]:
    if not isinstance(values, list):
        return []
    parsed: list[Language] = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            parsed.append(Language(value))
        except ValueError:
            continue
    return parsed


def _build_ingest_request(
    *,
    payload: WebhookEventRequest,
    source_channel: SourceChannel,
    fallback_phone: Optional[str],
) -> CandidateIngestRequest:
    data = payload.payload
    name = data.get("name") or data.get("candidate_name")
    phone = payload.phone or data.get("phone") or fallback_phone
    if not isinstance(name, str) or not name.strip():
        raise PermanentWebhookError("candidate lead missing name")
    if not isinstance(phone, str) or not phone.strip():
        raise PermanentWebhookError("candidate lead missing phone")

    request_data = {
        "name": name.strip(),
        "phone": phone.strip(),
        "source_channel": source_channel.value,
        "languages": _parse_languages(data.get("languages")),
        "therapy_experience": data.get("therapy_experience", []),
        "experience_years": data.get("experience_years", 0),
        "certifications": data.get("certifications", []),
        "expected_pay": data.get("expected_pay"),
        "current_location": data.get("current_location"),
        "preferred_shift_start": data.get("preferred_shift_start"),
        "preferred_shift_end": data.get("preferred_shift_end"),
        "referred_by": data.get("referred_by"),
        "last_employer": data.get("last_employer"),
        "job_id": data.get("job_id"),
    }
    try:
        return CandidateIngestRequest.model_validate(request_data)
    except ValidationError as exc:
        raise PermanentWebhookError(f"invalid candidate lead payload: {exc.errors()}") from exc


def _source_channel_for_event(*, channel: str, event_type: str) -> SourceChannel:
    if event_type == "referral_lead":
        return SourceChannel.referral
    if event_type == "call_lead":
        return SourceChannel.call
    return SourceChannel.whatsapp if channel == "whatsapp" else SourceChannel.call


def process_channel_event(
    *,
    store: InMemoryStore,
    channel: str,
    payload: WebhookEventRequest,
) -> str:
    if payload.payload.get("simulate_transient_error"):
        raise TransientWebhookError("provider timeout, retry needed")
    if payload.payload.get("simulate_permanent_error"):
        raise PermanentWebhookError("payload rejected by channel processor")

    event_type = (payload.event_type or "").strip().lower()
    if event_type not in {"candidate_lead", "referral_lead", "call_lead"}:
        return "ignored_event_type"

    source_channel = _source_channel_for_event(channel=channel, event_type=event_type)
    ingest_request = _build_ingest_request(
        payload=payload,
        source_channel=source_channel,
        fallback_phone=payload.phone,
    )
    if ingest_request.job_id:
        try:
            store.get_job(ingest_request.job_id)
        except StoreNotFoundError as exc:
            raise PermanentWebhookError(str(exc)) from exc

    candidate, deduplicated = store.ingest_candidate(ingest_request)
    if ingest_request.job_id:
        store.create_or_get_application(ingest_request.job_id, candidate.id)
    return f"candidate_upserted:{candidate.id}:dedup={str(deduplicated).lower()}"
