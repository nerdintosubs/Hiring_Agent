from __future__ import annotations

from backend.app.models import StageStatus

ALLOWED_TRANSITIONS = {
    StageStatus.new: {StageStatus.screened, StageStatus.dropped},
    StageStatus.screened: {
        StageStatus.interviewed,
        StageStatus.shortlisted,
        StageStatus.dropped,
    },
    StageStatus.interviewed: {StageStatus.shortlisted, StageStatus.dropped},
    StageStatus.shortlisted: {StageStatus.offered, StageStatus.dropped},
    StageStatus.offered: {StageStatus.joined, StageStatus.dropped},
    StageStatus.joined: set(),
    StageStatus.dropped: set(),
}

