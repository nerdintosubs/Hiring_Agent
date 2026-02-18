from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from backend.app.auth import AuthContext, require_roles
from backend.app.models import (
    CampaignBootstrapResponse,
    CampaignEventLogRequest,
    CampaignProgressResponse,
    CandidateIngestRequest,
    CandidateIngestResponse,
    EmployerIntakeRequest,
    EmployerIntakeResponse,
    FirstTenCampaignBootstrapRequest,
    InterviewScheduleRequest,
    InterviewScheduleResponse,
    ManualLeadCreateRequest,
    ManualLeadCreateResponse,
    ManualLeadItem,
    OfferCreateRequest,
    OfferCreateResponse,
    PipelineApplication,
    PipelineResponse,
    ScreeningRunRequest,
    ScreeningRunResponse,
    ShortlistGenerateRequest,
    ShortlistGenerateResponse,
    ShortlistItem,
    SourceChannel,
    StageStatus,
    StageTransitionRequest,
    WebhookEventRequest,
    WebhookEventResponse,
    WebsiteEventRequest,
    WebsiteEventResponse,
    WebsiteFunnelSummaryResponse,
    WebsiteLeadContactUpdateResponse,
    WebsiteLeadCreateRequest,
    WebsiteLeadCreateResponse,
    WebsiteLeadItem,
    WebsiteLeadQueueMode,
    utc_now,
)
from backend.app.observability import MetricsRegistry, configure_logging, observe_request
from backend.app.persistence import SqlitePersistence
from backend.app.services.channel_events import (
    PermanentWebhookError,
    TransientWebhookError,
    process_channel_event,
)
from backend.app.services.recaptcha import (
    RecaptchaServiceError,
    RecaptchaVerificationError,
    verify_recaptcha_token,
)
from backend.app.services.scoring import screening_score, shortlist_rank
from backend.app.services.webhooks import (
    SignatureVerificationError,
    verify_telephony_signature,
    verify_whatsapp_signature,
)
from backend.app.settings import Settings, load_settings
from backend.app.store import InMemoryStore, StoreConflictError, StoreNotFoundError


def create_app() -> FastAPI:
    app = FastAPI(title="Bangalore Hiring Agent API", version="0.1.0")
    configure_logging()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    settings = load_settings()
    persistence = SqlitePersistence(settings.database_url) if settings.persistence_enabled else None
    app.state.store = InMemoryStore(persistence=persistence)
    app.state.settings = settings
    app.state.metrics = MetricsRegistry()

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        return await observe_request(request, call_next, metrics=app.state.metrics)

    app.include_router(build_router())
    return app


def get_store(request: Request) -> InMemoryStore:
    return request.app.state.store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_metrics(request: Request) -> MetricsRegistry:
    return request.app.state.metrics


def default_target_funnel(target_joiners: int) -> dict[str, int]:
    return {
        "leads": target_joiners * 12,
        "screened": target_joiners * 6,
        "trials": target_joiners * 3,
        "offers": int(target_joiners * 1.5),
        "joined": target_joiners,
    }


def conversion_rates(counts: dict[str, int]) -> dict[str, float]:
    leads = max(counts.get("leads", 0), 1)
    screened = max(counts.get("screened", 0), 1)
    trials = max(counts.get("trials", 0), 1)
    offers = max(counts.get("offers", 0), 1)
    return {
        "lead_to_screened": round((counts.get("screened", 0) / leads) * 100, 2),
        "screened_to_trial": round((counts.get("trials", 0) / screened) * 100, 2),
        "trial_to_offer": round((counts.get("offers", 0) / trials) * 100, 2),
        "offer_to_joined": round((counts.get("joined", 0) / offers) * 100, 2),
    }


def campaign_health_status(
    *,
    counts: dict[str, int],
    target_joiners: int,
    target_funnel: dict[str, int],
) -> str:
    if counts.get("joined", 0) >= target_joiners:
        return "on_track"
    if counts.get("offers", 0) < max(target_funnel["offers"] // 3, 1):
        return "at_risk_offer_gap"
    if counts.get("screened", 0) < max(target_funnel["screened"] // 3, 1):
        return "at_risk_screening_gap"
    return "progressing"


def campaign_actions(counts: dict[str, int], target_funnel: dict[str, int]) -> list[str]:
    actions: list[str] = []
    if counts.get("leads", 0) < target_funnel["leads"]:
        actions.append("Boost lead gen via institutes, referrals, and WhatsApp groups daily.")
    if counts.get("screened", 0) < target_funnel["screened"]:
        actions.append("Add same-day multilingual phone screening slots to reduce drop-offs.")
    if counts.get("trials", 0) < target_funnel["trials"]:
        actions.append("Run daily trial blocks with backup candidates for no-show protection.")
    if counts.get("offers", 0) < target_funnel["offers"]:
        actions.append("Issue offer decisions within 4 hours after trial completion.")
    if counts.get("joined", 0) < target_funnel["joined"]:
        actions.append("Run T-24h and T-2h joining confirmations with safety and commute support.")
    return actions or ["Maintain current cadence and monitor conversion quality by source."]


def campaign_templates(whatsapp_business_number: str) -> dict[str, str]:
    return {
        "whatsapp_job_post": (
            "Hiring Female Fresher Therapists in Bangalore. Paid training, fixed salary + "
            "incentives, safe workplace, growth path. Apply on WhatsApp: "
            f"{whatsapp_business_number}"
        ),
        "screening_pitch_30s": (
            "We are hiring female fresher therapists for Bengaluru centers with paid training, "
            "safe shifts, and fast growth. Can we do a quick 5-minute screening call now?"
        ),
        "day_before_joining_nudge": (
            "Reminder: Your joining is tomorrow. Please confirm travel plan and reporting time. "
            "Reply YES to confirm."
        ),
    }


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready")
    def readiness(request: Request) -> dict[str, str]:
        settings = get_settings(request)
        persistence = getattr(request.app.state.store, "persistence", None)
        if settings.persistence_enabled and persistence and not persistence.ping():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            )
        return {"status": "ready"}

    @router.get("/metrics", response_class=PlainTextResponse)
    def metrics(request: Request) -> Response:
        registry = get_metrics(request)
        return PlainTextResponse(registry.to_prometheus())

    @router.post("/employers/intake", response_model=EmployerIntakeResponse)
    def employer_intake(
        payload: EmployerIntakeRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("employer", "recruiter", "admin")),
    ) -> EmployerIntakeResponse:
        store = get_store(request)
        employer, job = store.create_employer_and_job(payload)
        return EmployerIntakeResponse(
            employer_id=employer.id,
            job_id=job.id,
            sla_deadline_utc=job.sla_deadline_utc,
            normalized_role=job.role,
        )

    @router.post("/candidates/ingest", response_model=CandidateIngestResponse)
    def candidate_ingest(
        payload: CandidateIngestRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> CandidateIngestResponse:
        store = get_store(request)
        if payload.job_id:
            try:
                store.get_job(payload.job_id)
            except StoreNotFoundError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        candidate, deduplicated = store.ingest_candidate(payload)
        application_id = None
        if payload.job_id:
            application = store.create_or_get_application(payload.job_id, candidate.id)
            application_id = application.id
        return CandidateIngestResponse(
            candidate_id=candidate.id,
            deduplicated=deduplicated,
            application_id=application_id,
        )

    @router.post("/leads/manual", response_model=ManualLeadCreateResponse)
    def create_manual_lead(
        payload: ManualLeadCreateRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> ManualLeadCreateResponse:
        store = get_store(request)
        if payload.job_id:
            try:
                store.get_job(payload.job_id)
            except StoreNotFoundError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        lead, candidate, deduplicated = store.create_manual_lead(payload)
        return ManualLeadCreateResponse(
            lead_id=lead.id,
            candidate_id=candidate.id,
            deduplicated=deduplicated,
            application_id=lead.application_id,
        )

    @router.get("/leads/manual", response_model=list[ManualLeadItem])
    def list_manual_leads(
        request: Request,
        limit: int = 50,
        source_channel: Optional[SourceChannel] = None,
        neighborhood: Optional[str] = None,
        created_by: Optional[str] = None,
        search: Optional[str] = None,
        created_from: Optional[date] = None,
        created_to: Optional[date] = None,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> list[ManualLeadItem]:
        store = get_store(request)
        leads = store.list_manual_leads(
            limit=limit,
            source_channel=source_channel,
            neighborhood=neighborhood,
            created_by=created_by,
            search=search,
            created_from=created_from,
            created_to=created_to,
        )
        return [
            ManualLeadItem(
                lead_id=lead.id,
                source_channel=lead.source_channel,
                name=lead.name,
                phone=lead.phone,
                candidate_id=lead.candidate_id,
                deduplicated=lead.deduplicated,
                application_id=lead.application_id,
                job_id=lead.job_id,
                neighborhood=lead.neighborhood,
                notes=lead.notes,
                created_by=lead.created_by,
                created_at_utc=lead.created_at_utc,
            )
            for lead in leads
        ]

    @router.post("/leads/website", response_model=WebsiteLeadCreateResponse)
    def create_website_lead(
        payload: WebsiteLeadCreateRequest,
        request: Request,
    ) -> WebsiteLeadCreateResponse:
        store = get_store(request)
        settings = get_settings(request)
        if settings.recaptcha_enabled:
            if not settings.recaptcha_secret:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="recaptcha is enabled but secret is not configured",
                )
            if not payload.recaptcha_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="missing recaptcha token",
                )
            client_ip = request.client.host if request.client else None
            try:
                verify_recaptcha_token(
                    token=payload.recaptcha_token,
                    secret=settings.recaptcha_secret,
                    min_score=settings.recaptcha_min_score,
                    remote_ip=client_ip,
                    expected_action="therapist_apply",
                )
            except RecaptchaVerificationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=str(exc),
                ) from exc
            except RecaptchaServiceError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
        if payload.job_id:
            try:
                store.get_job(payload.job_id)
            except StoreNotFoundError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        try:
            lead, candidate, deduplicated = store.create_website_lead(
                payload,
                default_first_contact_sla_minutes=settings.default_first_contact_sla_minutes,
                default_whatsapp_number=settings.website_whatsapp_number,
            )
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return WebsiteLeadCreateResponse(
            lead_id=lead.id,
            candidate_id=candidate.id,
            deduplicated=deduplicated,
            application_id=lead.application_id,
            first_contact_due_utc=lead.first_contact_due_utc,
            first_contact_sla_minutes_effective=lead.first_contact_sla_minutes_effective,
            wa_link=lead.wa_link_generated,
        )

    @router.get("/leads/website", response_model=list[WebsiteLeadItem])
    def list_website_leads(
        request: Request,
        limit: int = 50,
        campaign_id: Optional[str] = None,
        queue_mode: WebsiteLeadQueueMode = WebsiteLeadQueueMode.all,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> list[WebsiteLeadItem]:
        store = get_store(request)
        leads = store.list_website_leads(
            limit=limit,
            campaign_id=campaign_id,
            queue_mode=queue_mode,
        )
        return [
            WebsiteLeadItem(
                lead_id=lead.id,
                candidate_id=lead.candidate_id,
                deduplicated=lead.deduplicated,
                application_id=lead.application_id,
                name=lead.name,
                phone=lead.phone,
                neighborhood=lead.neighborhood,
                campaign_id=lead.campaign_id,
                job_id=lead.job_id,
                utm_source=lead.utm_source,
                wa_link=lead.wa_link_generated,
                wa_click_count=lead.wa_click_count,
                first_contact_sla_minutes_effective=lead.first_contact_sla_minutes_effective,
                first_contact_due_utc=lead.first_contact_due_utc,
                first_contact_at_utc=lead.first_contact_at_utc,
                sla_breached=lead.sla_breached,
                created_at_utc=lead.created_at_utc,
            )
            for lead in leads
        ]

    @router.post(
        "/leads/website/{lead_id}/contact",
        response_model=WebsiteLeadContactUpdateResponse,
    )
    def mark_website_lead_contacted(
        lead_id: str,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> WebsiteLeadContactUpdateResponse:
        store = get_store(request)
        try:
            updated = store.mark_website_lead_contacted(lead_id=lead_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return WebsiteLeadContactUpdateResponse(
            lead_id=updated.id,
            first_contact_at_utc=updated.first_contact_at_utc or updated.updated_at_utc,
            sla_breached=updated.sla_breached,
        )

    @router.post("/events/website", response_model=WebsiteEventResponse)
    def record_website_event(
        payload: WebsiteEventRequest,
        request: Request,
    ) -> WebsiteEventResponse:
        store = get_store(request)
        try:
            event = store.record_website_event(payload)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return WebsiteEventResponse(event_id=event.id, recorded=True)

    @router.get("/funnel/website/summary", response_model=WebsiteFunnelSummaryResponse)
    def website_funnel_summary(
        request: Request,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        campaign_id: Optional[str] = None,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> WebsiteFunnelSummaryResponse:
        store = get_store(request)
        end = date_to or utc_now().date()
        start = date_from or (end - timedelta(days=6))
        if start > end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from cannot be greater than date_to",
            )
        summary = store.website_funnel_summary(
            date_from=start,
            date_to=end,
            campaign_id=campaign_id,
        )
        return WebsiteFunnelSummaryResponse.model_validate(summary)

    @router.post("/screening/run", response_model=ScreeningRunResponse)
    def run_screening(
        payload: ScreeningRunRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> ScreeningRunResponse:
        store = get_store(request)
        try:
            candidate = store.get_candidate(payload.candidate_id)
            job = store.get_job(payload.job_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        application = store.create_or_get_application(job.id, candidate.id)
        hard_pass, overall_score, explanation = screening_score(candidate, job)
        screening = store.create_screening(
            job_id=job.id,
            candidate_id=candidate.id,
            application_id=application.id,
            hard_filter_pass=hard_pass,
            overall_fit_score=overall_score,
            explanation=explanation,
        )
        store.set_screening_score(application.id, overall_score)
        to_stage = StageStatus.screened if hard_pass else StageStatus.dropped
        reason = "screening_passed" if hard_pass else "screening_failed"
        try:
            store.transition_application(application.id, to_stage, reason)
        except StoreConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return ScreeningRunResponse(
            screening_id=screening.id,
            application_id=application.id,
            hard_filter_pass=hard_pass,
            overall_fit_score=overall_score,
            explanation=explanation,
        )

    @router.post("/interviews/schedule", response_model=InterviewScheduleResponse)
    def schedule_interview(
        payload: InterviewScheduleRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> InterviewScheduleResponse:
        store = get_store(request)
        try:
            application = store.get_application_for_job_candidate(
                job_id=payload.job_id, candidate_id=payload.candidate_id
            )
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        if application.stage not in {StageStatus.screened, StageStatus.interviewed}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"interview cannot be scheduled from stage: {application.stage.value}",
            )

        interview = store.create_interview(
            application_id=application.id,
            mode=payload.mode,
            scheduled_at_utc=payload.scheduled_at_utc,
        )
        if application.stage != StageStatus.interviewed:
            store.transition_application(
                application.id,
                StageStatus.interviewed,
                reason="interview_scheduled",
            )
        return InterviewScheduleResponse(
            interview_id=interview.id,
            application_id=application.id,
            reminder_24h_utc=payload.scheduled_at_utc - timedelta(hours=24),
            reminder_2h_utc=payload.scheduled_at_utc - timedelta(hours=2),
        )

    @router.post("/shortlist/generate", response_model=ShortlistGenerateResponse)
    def generate_shortlist(
        payload: ShortlistGenerateRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> ShortlistGenerateResponse:
        store = get_store(request)
        try:
            store.get_job(payload.job_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        applications = [
            app
            for app in store.list_job_applications(payload.job_id)
            if app.stage in {StageStatus.screened, StageStatus.interviewed, StageStatus.shortlisted}
        ]
        ranked = []
        for application in applications:
            candidate = store.get_candidate(application.candidate_id)
            ranked.append(
                (
                    shortlist_rank(
                        screening_score_value=application.screening_score,
                        source_channel=candidate.source_channel.value,
                    ),
                    application,
                )
            )
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[: payload.top_k]
        output: list[ShortlistItem] = []
        for rank_score, application in selected:
            if application.stage != StageStatus.shortlisted:
                store.transition_application(
                    application.id, StageStatus.shortlisted, reason="shortlist_generated"
                )
            output.append(
                ShortlistItem(
                    candidate_id=application.candidate_id,
                    application_id=application.id,
                    rank_score=rank_score,
                )
            )
        return ShortlistGenerateResponse(job_id=payload.job_id, shortlisted=output)

    @router.post("/offers/create", response_model=OfferCreateResponse)
    def create_offer(
        payload: OfferCreateRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> OfferCreateResponse:
        store = get_store(request)
        try:
            application = store.get_application(payload.application_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        if application.stage not in {StageStatus.shortlisted, StageStatus.offered}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"offer cannot be created from stage: {application.stage.value}",
            )
        offer = store.create_offer(
            application_id=application.id,
            monthly_pay=payload.monthly_pay,
            joining_date=payload.joining_date,
        )
        if application.stage != StageStatus.offered:
            store.transition_application(
                application.id,
                StageStatus.offered,
                reason="offer_created",
            )
        return OfferCreateResponse(
            offer_id=offer.id,
            application_id=application.id,
            status=offer.status,
        )

    @router.post("/applications/{application_id}/stage")
    def transition_stage(
        application_id: str,
        payload: StageTransitionRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> dict[str, str]:
        store = get_store(request)
        try:
            updated = store.transition_application(application_id, payload.to_stage, payload.reason)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except StoreConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return {"application_id": updated.id, "stage": updated.stage.value}

    @router.get("/jobs/{job_id}/pipeline", response_model=PipelineResponse)
    def pipeline(
        job_id: str,
        request: Request,
        _: AuthContext = Depends(require_roles("employer", "recruiter", "admin")),
    ) -> PipelineResponse:
        store = get_store(request)
        try:
            store.get_job(job_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        applications = store.list_job_applications(job_id)
        counts = {stage: 0 for stage in StageStatus}
        items: list[PipelineApplication] = []
        for app_record in applications:
            counts[app_record.stage] += 1
            candidate = store.get_candidate(app_record.candidate_id)
            items.append(
                PipelineApplication(
                    application_id=app_record.id,
                    candidate_id=app_record.candidate_id,
                    stage=app_record.stage,
                    screening_score=app_record.screening_score,
                    source_channel=candidate.source_channel,
                )
            )
        return PipelineResponse(job_id=job_id, counts=counts, applications=items)

    @router.post("/webhooks/whatsapp", response_model=WebhookEventResponse)
    async def whatsapp_webhook(
        request: Request,
        _: AuthContext = Depends(require_roles("service", "admin")),
    ) -> WebhookEventResponse:
        store = get_store(request)
        settings = get_settings(request)
        raw_body = await request.body()
        try:
            verify_whatsapp_signature(
                headers=request.headers,
                raw_body=raw_body,
                secret=settings.whatsapp_webhook_secret,
            )
        except SignatureVerificationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        try:
            payload = WebhookEventRequest.model_validate(json.loads(raw_body.decode("utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid json payload",
            ) from exc

        existing = store.ensure_webhook_delivery(channel="whatsapp", event_id=payload.event_id)
        if existing.status.value == "processed":
            return WebhookEventResponse(status="duplicate", attempts=existing.attempts)
        if existing.status.value == "failed":
            return WebhookEventResponse(
                status="failed",
                attempts=existing.attempts,
                detail="max retries reached; manual intervention required",
            )

        try:
            detail = process_channel_event(store=store, channel="whatsapp", payload=payload)
            record = store.record_webhook_attempt(
                channel="whatsapp",
                event_id=payload.event_id,
                success=True,
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status="processed",
                attempts=record.attempts,
                detail=detail,
            )
        except TransientWebhookError as exc:
            record = store.record_webhook_attempt(
                channel="whatsapp",
                event_id=payload.event_id,
                success=False,
                transient=True,
                error=str(exc),
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status=record.status.value,
                attempts=record.attempts,
                next_retry_utc=record.next_retry_utc,
                detail=record.last_error,
            )
        except PermanentWebhookError as exc:
            record = store.record_webhook_attempt(
                channel="whatsapp",
                event_id=payload.event_id,
                success=False,
                transient=False,
                error=str(exc),
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status=record.status.value,
                attempts=record.attempts,
                detail=record.last_error,
            )

    @router.post("/webhooks/telephony", response_model=WebhookEventResponse)
    async def telephony_webhook(
        request: Request,
        _: AuthContext = Depends(require_roles("service", "admin")),
    ) -> WebhookEventResponse:
        store = get_store(request)
        settings = get_settings(request)
        raw_body = await request.body()
        try:
            verify_telephony_signature(
                headers=request.headers,
                raw_body=raw_body,
                secret=settings.telephony_webhook_secret,
            )
        except SignatureVerificationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        try:
            payload = WebhookEventRequest.model_validate(json.loads(raw_body.decode("utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid json payload",
            ) from exc

        existing = store.ensure_webhook_delivery(channel="telephony", event_id=payload.event_id)
        if existing.status.value == "processed":
            return WebhookEventResponse(status="duplicate", attempts=existing.attempts)
        if existing.status.value == "failed":
            return WebhookEventResponse(
                status="failed",
                attempts=existing.attempts,
                detail="max retries reached; manual intervention required",
            )

        try:
            detail = process_channel_event(store=store, channel="telephony", payload=payload)
            record = store.record_webhook_attempt(
                channel="telephony",
                event_id=payload.event_id,
                success=True,
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status="processed",
                attempts=record.attempts,
                detail=detail,
            )
        except TransientWebhookError as exc:
            record = store.record_webhook_attempt(
                channel="telephony",
                event_id=payload.event_id,
                success=False,
                transient=True,
                error=str(exc),
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status=record.status.value,
                attempts=record.attempts,
                next_retry_utc=record.next_retry_utc,
                detail=record.last_error,
            )
        except PermanentWebhookError as exc:
            record = store.record_webhook_attempt(
                channel="telephony",
                event_id=payload.event_id,
                success=False,
                transient=False,
                error=str(exc),
                max_retries=settings.webhook_max_retries,
                backoff_seconds=settings.webhook_retry_backoff_seconds,
            )
            return WebhookEventResponse(
                status=record.status.value,
                attempts=record.attempts,
                detail=record.last_error,
            )

    @router.post(
        "/campaigns/first-10/bootstrap",
        response_model=CampaignBootstrapResponse,
    )
    def bootstrap_first_ten_campaign(
        payload: FirstTenCampaignBootstrapRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> CampaignBootstrapResponse:
        store = get_store(request)
        settings = get_settings(request)
        campaign = store.create_first_ten_campaign(
            employer_name=payload.employer_name,
            city="Bangalore",
            neighborhood_focus=payload.neighborhood_focus,
            whatsapp_business_number=payload.whatsapp_business_number,
            target_joiners=payload.target_joiners,
            fresher_preferred=payload.fresher_preferred,
            first_contact_sla_minutes=payload.first_contact_sla_minutes,
        )
        effective_sla = (
            campaign.first_contact_sla_minutes or settings.default_first_contact_sla_minutes
        )
        return CampaignBootstrapResponse(
            campaign_id=campaign.id,
            city=campaign.city,
            target_joiners=campaign.target_joiners,
            first_contact_sla_minutes_effective=effective_sla,
            target_funnel=default_target_funnel(campaign.target_joiners),
            templates=campaign_templates(campaign.whatsapp_business_number),
        )

    @router.post(
        "/campaigns/{campaign_id}/events",
        response_model=CampaignProgressResponse,
    )
    def log_campaign_event(
        campaign_id: str,
        payload: CampaignEventLogRequest,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> CampaignProgressResponse:
        store = get_store(request)
        try:
            campaign = store.log_first_ten_event(
                campaign_id=campaign_id,
                event_type=payload.event_type,
                count=payload.count,
            )
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        target_funnel = default_target_funnel(campaign.target_joiners)
        return CampaignProgressResponse(
            campaign_id=campaign.id,
            employer_name=campaign.employer_name,
            city=campaign.city,
            target_joiners=campaign.target_joiners,
            counts=campaign.counts,
            conversion_rates=conversion_rates(campaign.counts),
            health_status=campaign_health_status(
                counts=campaign.counts,
                target_joiners=campaign.target_joiners,
                target_funnel=target_funnel,
            ),
            recommended_actions=campaign_actions(campaign.counts, target_funnel),
        )

    @router.get(
        "/campaigns/{campaign_id}/progress",
        response_model=CampaignProgressResponse,
    )
    def campaign_progress(
        campaign_id: str,
        request: Request,
        _: AuthContext = Depends(require_roles("recruiter", "admin")),
    ) -> CampaignProgressResponse:
        store = get_store(request)
        try:
            campaign = store.get_first_ten_campaign(campaign_id)
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        target_funnel = default_target_funnel(campaign.target_joiners)
        return CampaignProgressResponse(
            campaign_id=campaign.id,
            employer_name=campaign.employer_name,
            city=campaign.city,
            target_joiners=campaign.target_joiners,
            counts=campaign.counts,
            conversion_rates=conversion_rates(campaign.counts),
            health_status=campaign_health_status(
                counts=campaign.counts,
                target_joiners=campaign.target_joiners,
                target_funnel=target_funnel,
            ),
            recommended_actions=campaign_actions(campaign.counts, target_funnel),
        )

    return router


app = create_app()
