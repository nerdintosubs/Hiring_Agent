from __future__ import annotations

from datetime import date, datetime, timedelta
from threading import RLock
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from backend.app.models import (
    ApplicationRecord,
    AuditEventRecord,
    CampaignEventType,
    CandidateIngestRequest,
    CandidateRecord,
    EmployerIntakeRequest,
    EmployerRecord,
    FirstTenCampaignRecord,
    InterviewRecord,
    JobRecord,
    ManualLeadCreateRequest,
    ManualLeadRecord,
    OfferRecord,
    ScreeningRecord,
    SourceChannel,
    StageStatus,
    WebhookDeliveryRecord,
    WebhookProcessingStatus,
    utc_now,
)
from backend.app.services.dedupe import is_probable_duplicate
from backend.app.services.workflow import ALLOWED_TRANSITIONS

if TYPE_CHECKING:
    from backend.app.persistence import SqlitePersistence


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class StoreConflictError(Exception):
    pass


class StoreNotFoundError(Exception):
    pass


class InMemoryStore:
    def __init__(self, persistence: Optional["SqlitePersistence"] = None) -> None:
        self._lock = RLock()
        self.persistence = persistence
        self.employers: dict[str, EmployerRecord] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.candidates: dict[str, CandidateRecord] = {}
        self.applications: dict[str, ApplicationRecord] = {}
        self.screenings: dict[str, ScreeningRecord] = {}
        self.interviews: dict[str, InterviewRecord] = {}
        self.offers: dict[str, OfferRecord] = {}
        self.audit_events: list[AuditEventRecord] = []
        self.webhook_deliveries: dict[str, WebhookDeliveryRecord] = {}
        self.first_ten_campaigns: dict[str, FirstTenCampaignRecord] = {}
        self.manual_leads: dict[str, ManualLeadRecord] = {}

        if self.persistence:
            snapshot = self.persistence.load_snapshot()
            if snapshot:
                self._hydrate_from_snapshot(snapshot)
            else:
                for delivery in self.persistence.list_webhook_deliveries():
                    self.webhook_deliveries[delivery.key] = delivery
                for lead in self.persistence.list_manual_leads(limit=500):
                    self.manual_leads[lead.id] = lead

    def create_employer_and_job(
        self, request: EmployerIntakeRequest
    ) -> tuple[EmployerRecord, JobRecord]:
        with self._lock:
            now = utc_now()
            employer = EmployerRecord(
                id=new_id("emp"),
                name=request.employer_name.strip(),
                contact_phone=request.contact_phone.strip(),
                created_at_utc=now,
            )
            job = JobRecord(
                id=new_id("job"),
                employer_id=employer.id,
                role=request.role.strip().lower(),
                required_therapies=request.required_therapies,
                shift_start=request.shift_start,
                shift_end=request.shift_end,
                pay_min=request.pay_min,
                pay_max=request.pay_max,
                location_name=request.location_name,
                location=request.location,
                languages=request.languages,
                sla_deadline_utc=now + timedelta(hours=request.urgency_hours),
                created_at_utc=now,
            )
            self.employers[employer.id] = employer
            self.jobs[job.id] = job
            self._persist_state()
            return employer, job

    def get_job(self, job_id: str) -> JobRecord:
        job = self.jobs.get(job_id)
        if not job:
            raise StoreNotFoundError(f"job not found: {job_id}")
        return job

    def get_candidate(self, candidate_id: str) -> CandidateRecord:
        candidate = self.candidates.get(candidate_id)
        if not candidate:
            raise StoreNotFoundError(f"candidate not found: {candidate_id}")
        return candidate

    def get_application(self, application_id: str) -> ApplicationRecord:
        application = self.applications.get(application_id)
        if not application:
            raise StoreNotFoundError(f"application not found: {application_id}")
        return application

    def ingest_candidate(self, request: CandidateIngestRequest) -> tuple[CandidateRecord, bool]:
        with self._lock:
            for candidate in self.candidates.values():
                if is_probable_duplicate(
                    candidate,
                    phone=request.phone,
                    name=request.name,
                    last_employer=request.last_employer,
                ):
                    return candidate, True

            candidate = CandidateRecord(
                id=new_id("cand"),
                name=request.name.strip(),
                phone=request.phone.strip(),
                source_channel=request.source_channel,
                languages=request.languages,
                therapy_experience=request.therapy_experience,
                experience_years=request.experience_years,
                certifications=request.certifications,
                expected_pay=request.expected_pay,
                current_location=request.current_location,
                preferred_shift_start=request.preferred_shift_start,
                preferred_shift_end=request.preferred_shift_end,
                referred_by=request.referred_by,
                last_employer=request.last_employer,
                created_at_utc=utc_now(),
            )
            self.candidates[candidate.id] = candidate
            self._persist_state()
            return candidate, False

    def create_or_get_application(self, job_id: str, candidate_id: str) -> ApplicationRecord:
        with self._lock:
            for application in self.applications.values():
                if application.job_id == job_id and application.candidate_id == candidate_id:
                    return application

            now = utc_now()
            application = ApplicationRecord(
                id=new_id("app"),
                job_id=job_id,
                candidate_id=candidate_id,
                stage=StageStatus.new,
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.applications[application.id] = application
            self._add_audit_event(
                application_id=application.id,
                from_stage=None,
                to_stage=StageStatus.new,
                reason="application_created",
            )
            self._persist_state()
            return application

    def set_screening_score(self, application_id: str, score: float) -> ApplicationRecord:
        with self._lock:
            application = self.get_application(application_id)
            application.screening_score = score
            application.updated_at_utc = utc_now()
            self.applications[application.id] = application
            self._persist_state()
            return application

    def create_screening(
        self,
        *,
        job_id: str,
        candidate_id: str,
        application_id: str,
        hard_filter_pass: bool,
        overall_fit_score: float,
        explanation: list[str],
    ) -> ScreeningRecord:
        with self._lock:
            screening = ScreeningRecord(
                id=new_id("scr"),
                job_id=job_id,
                candidate_id=candidate_id,
                application_id=application_id,
                hard_filter_pass=hard_filter_pass,
                overall_fit_score=overall_fit_score,
                explanation=explanation,
                created_at_utc=utc_now(),
            )
            self.screenings[screening.id] = screening
            self._persist_state()
            return screening

    def create_interview(
        self, *, application_id: str, mode: str, scheduled_at_utc: datetime
    ) -> InterviewRecord:
        with self._lock:
            interview = InterviewRecord(
                id=new_id("int"),
                application_id=application_id,
                mode=mode,
                scheduled_at_utc=scheduled_at_utc,
                created_at_utc=utc_now(),
            )
            self.interviews[interview.id] = interview
            self._persist_state()
            return interview

    def create_offer(
        self, *, application_id: str, monthly_pay: int, joining_date: date
    ) -> OfferRecord:
        with self._lock:
            for offer in self.offers.values():
                if offer.application_id == application_id:
                    return offer
            offer = OfferRecord(
                id=new_id("off"),
                application_id=application_id,
                monthly_pay=monthly_pay,
                joining_date=joining_date,
                status="pending_acceptance",
                created_at_utc=utc_now(),
            )
            self.offers[offer.id] = offer
            self._persist_state()
            return offer

    def transition_application(
        self, application_id: str, to_stage: StageStatus, reason: str
    ) -> ApplicationRecord:
        with self._lock:
            application = self.get_application(application_id)
            if application.stage == to_stage:
                return application
            allowed = ALLOWED_TRANSITIONS[application.stage]
            if to_stage not in allowed:
                raise StoreConflictError(
                    f"invalid transition {application.stage.value} -> {to_stage.value}"
                )
            from_stage = application.stage
            application.stage = to_stage
            application.updated_at_utc = utc_now()
            self.applications[application.id] = application
            self._add_audit_event(
                application_id=application.id,
                from_stage=from_stage,
                to_stage=to_stage,
                reason=reason,
            )
            self._persist_state()
            return application

    def get_application_for_job_candidate(
        self, *, job_id: str, candidate_id: str
    ) -> ApplicationRecord:
        for application in self.applications.values():
            if application.job_id == job_id and application.candidate_id == candidate_id:
                return application
        raise StoreNotFoundError(
            f"application not found for job {job_id} and candidate {candidate_id}"
        )

    def list_job_applications(self, job_id: str) -> list[ApplicationRecord]:
        return [
            application
            for application in self.applications.values()
            if application.job_id == job_id
        ]

    def list_audit_events(self, application_id: str) -> list[AuditEventRecord]:
        return [event for event in self.audit_events if event.application_id == application_id]

    def get_webhook_delivery(
        self, *, channel: str, event_id: str
    ) -> Optional[WebhookDeliveryRecord]:
        key = self._webhook_key(channel=channel, event_id=event_id)
        return self.webhook_deliveries.get(key)

    def ensure_webhook_delivery(self, *, channel: str, event_id: str) -> WebhookDeliveryRecord:
        with self._lock:
            key = self._webhook_key(channel=channel, event_id=event_id)
            existing = self.webhook_deliveries.get(key)
            if existing:
                return existing
            now = utc_now()
            record = WebhookDeliveryRecord(
                id=new_id("whk"),
                key=key,
                channel=channel,
                event_id=event_id,
                status=WebhookProcessingStatus.received,
                attempts=0,
                last_error=None,
                next_retry_utc=None,
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.webhook_deliveries[key] = record
            self._persist_webhook_delivery(record)
            self._persist_state()
            return record

    def record_webhook_attempt(
        self,
        *,
        channel: str,
        event_id: str,
        success: bool,
        error: Optional[str] = None,
        transient: bool = False,
        max_retries: int = 3,
        backoff_seconds: int = 60,
    ) -> WebhookDeliveryRecord:
        with self._lock:
            key = self._webhook_key(channel=channel, event_id=event_id)
            record = self.webhook_deliveries.get(key)
            if not record:
                now = utc_now()
                record = WebhookDeliveryRecord(
                    id=new_id("whk"),
                    key=key,
                    channel=channel,
                    event_id=event_id,
                    status=WebhookProcessingStatus.received,
                    attempts=0,
                    last_error=None,
                    next_retry_utc=None,
                    created_at_utc=now,
                    updated_at_utc=now,
                )
                self.webhook_deliveries[key] = record

            attempts = record.attempts + 1
            if success:
                status = WebhookProcessingStatus.processed
                next_retry = None
                last_error = None
            else:
                last_error = error or "unknown webhook processing error"
                if transient and attempts < max_retries:
                    status = WebhookProcessingStatus.retry_pending
                    next_retry = utc_now() + timedelta(seconds=backoff_seconds * attempts)
                else:
                    status = WebhookProcessingStatus.failed
                    next_retry = None

            updated = record.model_copy(
                update={
                    "attempts": attempts,
                    "status": status,
                    "last_error": last_error,
                    "next_retry_utc": next_retry,
                    "updated_at_utc": utc_now(),
                }
            )
            self.webhook_deliveries[key] = updated
            self._persist_webhook_delivery(updated)
            self._persist_state()
            return updated

    def register_webhook_event(self, event_id: str) -> bool:
        # Backward-compatible helper for legacy tests/callers.
        existing = self.get_webhook_delivery(channel="legacy", event_id=event_id)
        if existing and existing.status == WebhookProcessingStatus.processed:
            return True
        self.record_webhook_attempt(channel="legacy", event_id=event_id, success=True)
        return False

    def create_first_ten_campaign(
        self,
        *,
        employer_name: str,
        city: str,
        neighborhood_focus: list[str],
        whatsapp_business_number: str,
        target_joiners: int,
        fresher_preferred: bool,
    ) -> FirstTenCampaignRecord:
        with self._lock:
            now = utc_now()
            campaign = FirstTenCampaignRecord(
                id=new_id("cmp"),
                employer_name=employer_name.strip(),
                city=city,
                neighborhood_focus=neighborhood_focus,
                whatsapp_business_number=whatsapp_business_number.strip(),
                target_joiners=target_joiners,
                fresher_preferred=fresher_preferred,
                counts={
                    CampaignEventType.leads.value: 0,
                    CampaignEventType.screened.value: 0,
                    CampaignEventType.trials.value: 0,
                    CampaignEventType.offers.value: 0,
                    CampaignEventType.joined.value: 0,
                },
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.first_ten_campaigns[campaign.id] = campaign
            self._persist_state()
            return campaign

    def create_manual_lead(
        self, request: ManualLeadCreateRequest
    ) -> tuple[ManualLeadRecord, CandidateRecord, bool]:
        candidate_request = CandidateIngestRequest(
            name=request.name,
            phone=request.phone,
            source_channel=request.source_channel,
            languages=request.languages,
            therapy_experience=request.therapy_experience,
            experience_years=request.experience_years,
            certifications=request.certifications,
            expected_pay=request.expected_pay,
            current_location=request.current_location,
            preferred_shift_start=request.preferred_shift_start,
            preferred_shift_end=request.preferred_shift_end,
            referred_by=request.referred_by,
            last_employer=request.last_employer,
            job_id=request.job_id,
        )
        candidate, deduplicated = self.ingest_candidate(candidate_request)
        application_id = None
        if request.job_id:
            application = self.create_or_get_application(request.job_id, candidate.id)
            application_id = application.id
        lead = ManualLeadRecord(
            id=new_id("lead"),
            source_channel=request.source_channel,
            name=request.name.strip(),
            phone=request.phone.strip(),
            languages=request.languages,
            therapy_experience=request.therapy_experience,
            experience_years=request.experience_years,
            certifications=request.certifications,
            expected_pay=request.expected_pay,
            current_location=request.current_location,
            preferred_shift_start=request.preferred_shift_start,
            preferred_shift_end=request.preferred_shift_end,
            referred_by=request.referred_by,
            last_employer=request.last_employer,
            job_id=request.job_id,
            neighborhood=request.neighborhood,
            notes=request.notes,
            created_by=request.created_by,
            candidate_id=candidate.id,
            deduplicated=deduplicated,
            application_id=application_id,
            created_at_utc=utc_now(),
        )
        with self._lock:
            self.manual_leads[lead.id] = lead
        self._persist_manual_lead(lead)
        self._persist_state()
        return lead, candidate, deduplicated

    def list_manual_leads(
        self,
        *,
        limit: int = 50,
        source_channel: Optional[SourceChannel] = None,
        neighborhood: Optional[str] = None,
        created_by: Optional[str] = None,
        search: Optional[str] = None,
        created_from: Optional[date] = None,
        created_to: Optional[date] = None,
    ) -> list[ManualLeadRecord]:
        with self._lock:
            records = list(self.manual_leads.values())
        if source_channel:
            records = [item for item in records if item.source_channel == source_channel]
        if neighborhood:
            target = neighborhood.strip().lower()
            records = [
                item
                for item in records
                if item.neighborhood and target in item.neighborhood.lower()
            ]
        if created_by:
            target = created_by.strip().lower()
            records = [
                item for item in records if item.created_by and target in item.created_by.lower()
            ]
        if search:
            term = search.strip().lower()
            records = [
                item
                for item in records
                if (
                    term in item.name.lower()
                    or term in item.phone.lower()
                    or (item.notes and term in item.notes.lower())
                    or term in item.id.lower()
                    or term in item.candidate_id.lower()
                    or (item.job_id and term in item.job_id.lower())
                )
            ]
        if created_from:
            records = [
                item for item in records if item.created_at_utc.date() >= created_from
            ]
        if created_to:
            records = [item for item in records if item.created_at_utc.date() <= created_to]
        records.sort(key=lambda item: item.created_at_utc, reverse=True)
        safe_limit = max(1, min(limit, 500))
        return records[:safe_limit]

    def get_first_ten_campaign(self, campaign_id: str) -> FirstTenCampaignRecord:
        campaign = self.first_ten_campaigns.get(campaign_id)
        if not campaign:
            raise StoreNotFoundError(f"campaign not found: {campaign_id}")
        return campaign

    def log_first_ten_event(
        self,
        *,
        campaign_id: str,
        event_type: CampaignEventType,
        count: int,
    ) -> FirstTenCampaignRecord:
        with self._lock:
            campaign = self.get_first_ten_campaign(campaign_id)
            updated_counts = dict(campaign.counts)
            updated_counts[event_type.value] = updated_counts.get(event_type.value, 0) + count
            campaign = campaign.model_copy(
                update={"counts": updated_counts, "updated_at_utc": utc_now()}
            )
            self.first_ten_campaigns[campaign_id] = campaign
            self._persist_state()
            return campaign

    def _add_audit_event(
        self,
        *,
        application_id: str,
        from_stage: Optional[StageStatus],
        to_stage: StageStatus,
        reason: str,
    ) -> None:
        event = AuditEventRecord(
            id=new_id("aud"),
            application_id=application_id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
            created_at_utc=utc_now(),
        )
        self.audit_events.append(event)

    def _persist_webhook_delivery(self, record: WebhookDeliveryRecord) -> None:
        if self.persistence:
            self.persistence.upsert_webhook_delivery(record)

    def _persist_manual_lead(self, record: ManualLeadRecord) -> None:
        if self.persistence:
            self.persistence.insert_manual_lead(record)

    def _persist_state(self) -> None:
        if not self.persistence:
            return
        with self._lock:
            self.persistence.save_snapshot(self._snapshot_data())

    def _snapshot_data(self) -> dict:
        return {
            "employers": [record.model_dump(mode="json") for record in self.employers.values()],
            "jobs": [record.model_dump(mode="json") for record in self.jobs.values()],
            "candidates": [record.model_dump(mode="json") for record in self.candidates.values()],
            "applications": [
                record.model_dump(mode="json") for record in self.applications.values()
            ],
            "screenings": [record.model_dump(mode="json") for record in self.screenings.values()],
            "interviews": [record.model_dump(mode="json") for record in self.interviews.values()],
            "offers": [record.model_dump(mode="json") for record in self.offers.values()],
            "audit_events": [record.model_dump(mode="json") for record in self.audit_events],
            "webhook_deliveries": [
                record.model_dump(mode="json") for record in self.webhook_deliveries.values()
            ],
            "first_ten_campaigns": [
                record.model_dump(mode="json")
                for record in self.first_ten_campaigns.values()
            ],
            "manual_leads": [
                record.model_dump(mode="json") for record in self.manual_leads.values()
            ],
        }

    def _hydrate_from_snapshot(self, snapshot: dict) -> None:
        self.employers = {
            record["id"]: EmployerRecord.model_validate(record)
            for record in snapshot.get("employers", [])
        }
        self.jobs = {
            record["id"]: JobRecord.model_validate(record)
            for record in snapshot.get("jobs", [])
        }
        self.candidates = {
            record["id"]: CandidateRecord.model_validate(record)
            for record in snapshot.get("candidates", [])
        }
        self.applications = {
            record["id"]: ApplicationRecord.model_validate(record)
            for record in snapshot.get("applications", [])
        }
        self.screenings = {
            record["id"]: ScreeningRecord.model_validate(record)
            for record in snapshot.get("screenings", [])
        }
        self.interviews = {
            record["id"]: InterviewRecord.model_validate(record)
            for record in snapshot.get("interviews", [])
        }
        self.offers = {
            record["id"]: OfferRecord.model_validate(record)
            for record in snapshot.get("offers", [])
        }
        self.audit_events = [
            AuditEventRecord.model_validate(record) for record in snapshot.get("audit_events", [])
        ]
        self.webhook_deliveries = {
            record["key"]: WebhookDeliveryRecord.model_validate(record)
            for record in snapshot.get("webhook_deliveries", [])
        }
        self.first_ten_campaigns = {
            record["id"]: FirstTenCampaignRecord.model_validate(record)
            for record in snapshot.get("first_ten_campaigns", [])
        }
        self.manual_leads = {
            record["id"]: ManualLeadRecord.model_validate(record)
            for record in snapshot.get("manual_leads", [])
        }

    @staticmethod
    def _webhook_key(*, channel: str, event_id: str) -> str:
        return f"{channel}:{event_id}"
