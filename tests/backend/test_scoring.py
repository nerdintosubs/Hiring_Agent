from __future__ import annotations

from backend.app.models import (
    CandidateRecord,
    Coordinates,
    JobRecord,
    Language,
    SourceChannel,
    utc_now,
)
from backend.app.services.scoring import compute_commute_score, shortlist_rank


def test_commute_score_prefers_nearby_candidates() -> None:
    job = JobRecord(
        id="job_1",
        employer_id="emp_1",
        role="therapist",
        required_therapies=[],
        shift_start="10:00",
        shift_end="19:00",
        pay_min=20000,
        pay_max=30000,
        location_name="Indiranagar",
        location=Coordinates(lat=12.9719, lon=77.6412),
        languages=[Language.en],
        sla_deadline_utc=utc_now(),
        created_at_utc=utc_now(),
    )
    near = CandidateRecord(
        id="cand_1",
        name="Near Candidate",
        phone="1234567890",
        source_channel=SourceChannel.referral,
        languages=[Language.en],
        therapy_experience=[],
        experience_years=1,
        certifications=[],
        expected_pay=25000,
        current_location=Coordinates(lat=12.9721, lon=77.642),
        preferred_shift_start=None,
        preferred_shift_end=None,
        referred_by=None,
        last_employer=None,
        created_at_utc=utc_now(),
    )
    far = near.model_copy(
        update={
            "id": "cand_2",
            "current_location": Coordinates(lat=13.2, lon=77.2),
        }
    )
    assert compute_commute_score(near, job) > compute_commute_score(far, job)


def test_shortlist_rank_includes_source_signal() -> None:
    referral_rank = shortlist_rank(0.8, "referral")
    web_rank = shortlist_rank(0.8, "web")
    assert referral_rank > web_rank
