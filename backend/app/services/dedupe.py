from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

from backend.app.models import CandidateRecord


def normalize(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def is_probable_duplicate(
    existing: CandidateRecord,
    *,
    phone: str,
    name: str,
    last_employer: Optional[str],
) -> bool:
    if normalize(existing.phone) == normalize(phone):
        return True

    existing_name = normalize(existing.name)
    incoming_name = normalize(name)
    if not existing_name or not incoming_name:
        return False

    name_ratio = SequenceMatcher(a=existing_name, b=incoming_name).ratio()
    if name_ratio < 0.9:
        return False

    if normalize(existing.last_employer) and normalize(last_employer):
        return normalize(existing.last_employer) == normalize(last_employer)

    return True
