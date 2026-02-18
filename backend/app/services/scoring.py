from __future__ import annotations

import math
from typing import Optional

from backend.app.models import CandidateRecord, JobRecord

SOURCE_RELIABILITY = {
    "referral": 0.9,
    "walk_in": 0.8,
    "whatsapp": 0.75,
    "call": 0.7,
    "agent": 0.6,
    "web": 0.55,
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def compute_commute_score(candidate: CandidateRecord, job: JobRecord) -> float:
    if not candidate.current_location:
        return 0.5
    distance = haversine_km(
        candidate.current_location.lat,
        candidate.current_location.lon,
        job.location.lat,
        job.location.lon,
    )
    if distance <= 5:
        return 1.0
    if distance <= 10:
        return 0.8
    if distance <= 20:
        return 0.5
    if distance <= 30:
        return 0.2
    return 0.0


def screening_score(candidate: CandidateRecord, job: JobRecord) -> tuple[bool, float, list[str]]:
    required_therapies = {value.lower().strip() for value in job.required_therapies}
    candidate_therapies = {value.lower().strip() for value in candidate.therapy_experience}
    matched_therapies = required_therapies.intersection(candidate_therapies)
    therapy_score = (
        len(matched_therapies) / len(required_therapies) if required_therapies else 1.0
    )

    required_languages = set(job.languages)
    candidate_languages = set(candidate.languages)
    language_matches = required_languages.intersection(candidate_languages)
    language_score = (
        len(language_matches) / len(required_languages) if required_languages else 1.0
    )

    cert_or_exp_ok = bool(candidate.certifications) or candidate.experience_years >= 2
    compliance_score = 1.0 if cert_or_exp_ok else 0.3
    commute_score = compute_commute_score(candidate, job)

    overall = round(
        0.35 * therapy_score
        + 0.25 * language_score
        + 0.20 * commute_score
        + 0.20 * compliance_score,
        3,
    )

    hard_pass = (
        therapy_score >= 1.0
        and (language_score > 0.0 or not required_languages)
        and cert_or_exp_ok
    )
    explanation = [
        f"therapy_score={therapy_score:.2f}",
        f"language_score={language_score:.2f}",
        f"commute_score={commute_score:.2f}",
        f"cert_or_exp_ok={cert_or_exp_ok}",
    ]
    return hard_pass, overall, explanation


def shortlist_rank(screening_score_value: Optional[float], source_channel: str) -> float:
    base = screening_score_value if screening_score_value is not None else 0.0
    source_weight = SOURCE_RELIABILITY.get(source_channel, 0.5)
    return round(base + 0.1 * source_weight, 3)
