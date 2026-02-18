from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.utcnow()


class Language(str, Enum):
    kn = "kn"
    en = "en"
    hi = "hi"
    ta = "ta"
    te = "te"


class SourceChannel(str, Enum):
    whatsapp = "whatsapp"
    walk_in = "walk_in"
    referral = "referral"
    agent = "agent"
    web = "web"
    call = "call"


class StageStatus(str, Enum):
    new = "new"
    screened = "screened"
    interviewed = "interviewed"
    shortlisted = "shortlisted"
    offered = "offered"
    joined = "joined"
    dropped = "dropped"


class Coordinates(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class EmployerIntakeRequest(BaseModel):
    employer_name: str = Field(min_length=2, max_length=120)
    contact_phone: str = Field(min_length=8, max_length=20)
    role: str = Field(min_length=2, max_length=80)
    required_therapies: list[str] = Field(default_factory=list)
    shift_start: str = Field(description="24h HH:MM")
    shift_end: str = Field(description="24h HH:MM")
    pay_min: int = Field(ge=1)
    pay_max: int = Field(ge=1)
    location_name: str = Field(min_length=2, max_length=120)
    location: Coordinates
    languages: list[Language] = Field(default_factory=list)
    urgency_hours: int = Field(default=48, ge=1, le=168)

    @model_validator(mode="after")
    def validate_pay_band(self) -> "EmployerIntakeRequest":
        if self.pay_min > self.pay_max:
            raise ValueError("pay_min cannot be greater than pay_max")
        return self


class EmployerIntakeResponse(BaseModel):
    employer_id: str
    job_id: str
    sla_deadline_utc: datetime
    normalized_role: str


class CandidateIngestRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    source_channel: SourceChannel
    languages: list[Language] = Field(default_factory=list)
    therapy_experience: list[str] = Field(default_factory=list)
    experience_years: float = Field(default=0, ge=0, le=50)
    certifications: list[str] = Field(default_factory=list)
    expected_pay: Optional[int] = Field(default=None, ge=1)
    current_location: Optional[Coordinates] = None
    preferred_shift_start: Optional[str] = None
    preferred_shift_end: Optional[str] = None
    referred_by: Optional[str] = None
    last_employer: Optional[str] = None
    job_id: Optional[str] = None


class CandidateIngestResponse(BaseModel):
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]


class ScreeningRunRequest(BaseModel):
    candidate_id: str
    job_id: str


class ScreeningRunResponse(BaseModel):
    screening_id: str
    application_id: str
    hard_filter_pass: bool
    overall_fit_score: float
    explanation: list[str]


class InterviewScheduleRequest(BaseModel):
    job_id: str
    candidate_id: str
    mode: str = Field(default="phone")
    scheduled_at_utc: datetime


class InterviewScheduleResponse(BaseModel):
    interview_id: str
    application_id: str
    reminder_24h_utc: datetime
    reminder_2h_utc: datetime


class ShortlistGenerateRequest(BaseModel):
    job_id: str
    top_k: int = Field(default=5, ge=1, le=50)


class ShortlistItem(BaseModel):
    candidate_id: str
    application_id: str
    rank_score: float
    requires_recruiter_approval: bool = True


class ShortlistGenerateResponse(BaseModel):
    job_id: str
    shortlisted: list[ShortlistItem]


class OfferCreateRequest(BaseModel):
    application_id: str
    monthly_pay: int = Field(ge=1)
    joining_date: date


class OfferCreateResponse(BaseModel):
    offer_id: str
    application_id: str
    status: str


class StageTransitionRequest(BaseModel):
    to_stage: StageStatus
    reason: str = Field(min_length=2, max_length=200)


class PipelineApplication(BaseModel):
    application_id: str
    candidate_id: str
    stage: StageStatus
    screening_score: Optional[float]
    source_channel: SourceChannel


class PipelineResponse(BaseModel):
    job_id: str
    counts: dict[StageStatus, int]
    applications: list[PipelineApplication]


class WebhookEventRequest(BaseModel):
    event_id: str = Field(min_length=4, max_length=120)
    phone: Optional[str] = None
    event_type: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookEventResponse(BaseModel):
    status: str
    attempts: Optional[int] = None
    next_retry_utc: Optional[datetime] = None
    detail: Optional[str] = None


class WebhookProcessingStatus(str, Enum):
    received = "received"
    processed = "processed"
    retry_pending = "retry_pending"
    failed = "failed"


class CampaignEventType(str, Enum):
    leads = "leads"
    screened = "screened"
    trials = "trials"
    offers = "offers"
    joined = "joined"


class WebsiteEventType(str, Enum):
    view = "view"
    cta_click = "cta_click"
    form_start = "form_start"
    form_submit = "form_submit"
    wa_click = "wa_click"


class WebsiteLeadQueueMode(str, Enum):
    all = "all"
    due_soon = "due_soon"
    overdue = "overdue"
    hot_new = "hot_new"


class FirstTenCampaignBootstrapRequest(BaseModel):
    employer_name: str = Field(min_length=2, max_length=120)
    neighborhood_focus: list[str] = Field(default_factory=list)
    whatsapp_business_number: str = Field(min_length=8, max_length=20)
    target_joiners: int = Field(default=10, ge=1, le=200)
    fresher_preferred: bool = True
    first_contact_sla_minutes: Optional[int] = Field(default=None, ge=5, le=240)


class CampaignBootstrapResponse(BaseModel):
    campaign_id: str
    city: str
    target_joiners: int
    first_contact_sla_minutes_effective: int
    target_funnel: dict[str, int]
    templates: dict[str, str]


class CampaignEventLogRequest(BaseModel):
    event_type: CampaignEventType
    count: int = Field(default=1, ge=1, le=200)
    note: Optional[str] = Field(default=None, max_length=200)


class CampaignProgressResponse(BaseModel):
    campaign_id: str
    employer_name: str
    city: str
    target_joiners: int
    counts: dict[str, int]
    conversion_rates: dict[str, float]
    health_status: str
    recommended_actions: list[str]


class ManualLeadCreateRequest(BaseModel):
    source_channel: SourceChannel = SourceChannel.walk_in
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    languages: list[Language] = Field(default_factory=list)
    therapy_experience: list[str] = Field(default_factory=list)
    experience_years: float = Field(default=0, ge=0, le=50)
    certifications: list[str] = Field(default_factory=list)
    expected_pay: Optional[int] = Field(default=None, ge=1)
    current_location: Optional[Coordinates] = None
    preferred_shift_start: Optional[str] = None
    preferred_shift_end: Optional[str] = None
    referred_by: Optional[str] = None
    last_employer: Optional[str] = None
    job_id: Optional[str] = None
    neighborhood: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=250)
    created_by: Optional[str] = Field(default=None, max_length=120)


class ManualLeadCreateResponse(BaseModel):
    lead_id: str
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]


class ManualLeadItem(BaseModel):
    lead_id: str
    source_channel: SourceChannel
    name: str
    phone: str
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]
    job_id: Optional[str]
    neighborhood: Optional[str]
    notes: Optional[str]
    created_by: Optional[str]
    created_at_utc: datetime


class WebsiteLeadCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    languages: list[Language] = Field(default_factory=list)
    therapy_experience: list[str] = Field(default_factory=list)
    experience_years: float = Field(default=0, ge=0, le=50)
    certifications: list[str] = Field(default_factory=list)
    expected_pay: Optional[int] = Field(default=None, ge=1)
    current_location: Optional[Coordinates] = None
    preferred_shift_start: Optional[str] = None
    preferred_shift_end: Optional[str] = None
    neighborhood: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=250)
    job_id: Optional[str] = None
    campaign_id: Optional[str] = None
    utm_source: Optional[str] = Field(default=None, max_length=120)
    utm_medium: Optional[str] = Field(default=None, max_length=120)
    utm_campaign: Optional[str] = Field(default=None, max_length=120)
    utm_term: Optional[str] = Field(default=None, max_length=120)
    utm_content: Optional[str] = Field(default=None, max_length=120)
    landing_path: Optional[str] = Field(default=None, max_length=250)
    referrer: Optional[str] = Field(default=None, max_length=250)
    session_id: Optional[str] = Field(default=None, max_length=120)
    recaptcha_token: Optional[str] = Field(default=None, max_length=4000)


class WebsiteLeadCreateResponse(BaseModel):
    lead_id: str
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]
    first_contact_due_utc: datetime
    first_contact_sla_minutes_effective: int
    wa_link: str


class WebsiteLeadItem(BaseModel):
    lead_id: str
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]
    name: str
    phone: str
    neighborhood: Optional[str]
    campaign_id: Optional[str]
    job_id: Optional[str]
    utm_source: Optional[str]
    wa_link: str
    wa_click_count: int
    first_contact_sla_minutes_effective: int
    first_contact_due_utc: datetime
    first_contact_at_utc: Optional[datetime]
    sla_breached: bool
    created_at_utc: datetime


class WebsiteLeadContactUpdateResponse(BaseModel):
    lead_id: str
    first_contact_at_utc: datetime
    sla_breached: bool


class WebsiteEventRequest(BaseModel):
    event_type: WebsiteEventType
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    session_id: Optional[str] = Field(default=None, max_length=120)
    utm_source: Optional[str] = Field(default=None, max_length=120)
    utm_medium: Optional[str] = Field(default=None, max_length=120)
    utm_campaign: Optional[str] = Field(default=None, max_length=120)
    landing_path: Optional[str] = Field(default=None, max_length=250)
    referrer: Optional[str] = Field(default=None, max_length=250)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebsiteEventResponse(BaseModel):
    event_id: str
    recorded: bool


class WebsiteFunnelSummaryResponse(BaseModel):
    date_from: date
    date_to: date
    total_leads: int
    open_leads: int
    contacted_leads: int
    breached_leads: int
    within_sla_rate: float
    event_counts: dict[str, int]
    leads_by_source: dict[str, int]
    leads_by_neighborhood: dict[str, int]


class EmployerRecord(BaseModel):
    id: str
    name: str
    contact_phone: str
    created_at_utc: datetime


class JobRecord(BaseModel):
    id: str
    employer_id: str
    role: str
    required_therapies: list[str]
    shift_start: str
    shift_end: str
    pay_min: int
    pay_max: int
    location_name: str
    location: Coordinates
    languages: list[Language]
    sla_deadline_utc: datetime
    created_at_utc: datetime


class CandidateRecord(BaseModel):
    id: str
    name: str
    phone: str
    source_channel: SourceChannel
    languages: list[Language]
    therapy_experience: list[str]
    experience_years: float
    certifications: list[str]
    expected_pay: Optional[int]
    current_location: Optional[Coordinates]
    preferred_shift_start: Optional[str]
    preferred_shift_end: Optional[str]
    referred_by: Optional[str]
    last_employer: Optional[str]
    created_at_utc: datetime


class ApplicationRecord(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    stage: StageStatus = StageStatus.new
    screening_score: Optional[float] = None
    created_at_utc: datetime
    updated_at_utc: datetime


class ScreeningRecord(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    application_id: str
    hard_filter_pass: bool
    overall_fit_score: float
    explanation: list[str]
    created_at_utc: datetime


class InterviewRecord(BaseModel):
    id: str
    application_id: str
    mode: str
    scheduled_at_utc: datetime
    created_at_utc: datetime


class OfferRecord(BaseModel):
    id: str
    application_id: str
    monthly_pay: int
    joining_date: date
    status: str
    created_at_utc: datetime


class AuditEventRecord(BaseModel):
    id: str
    application_id: str
    from_stage: Optional[StageStatus]
    to_stage: StageStatus
    reason: str
    created_at_utc: datetime


class WebhookDeliveryRecord(BaseModel):
    id: str
    key: str
    channel: str
    event_id: str
    status: WebhookProcessingStatus
    attempts: int
    last_error: Optional[str]
    next_retry_utc: Optional[datetime]
    created_at_utc: datetime
    updated_at_utc: datetime


class FirstTenCampaignRecord(BaseModel):
    id: str
    employer_name: str
    city: str
    neighborhood_focus: list[str]
    whatsapp_business_number: str
    target_joiners: int
    fresher_preferred: bool
    first_contact_sla_minutes: Optional[int] = None
    counts: dict[str, int]
    created_at_utc: datetime
    updated_at_utc: datetime


class ManualLeadRecord(BaseModel):
    id: str
    source_channel: SourceChannel
    name: str
    phone: str
    languages: list[Language]
    therapy_experience: list[str]
    experience_years: float
    certifications: list[str]
    expected_pay: Optional[int]
    current_location: Optional[Coordinates]
    preferred_shift_start: Optional[str]
    preferred_shift_end: Optional[str]
    referred_by: Optional[str]
    last_employer: Optional[str]
    job_id: Optional[str]
    neighborhood: Optional[str]
    notes: Optional[str]
    created_by: Optional[str]
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]
    created_at_utc: datetime


class WebsiteLeadRecord(BaseModel):
    id: str
    candidate_id: str
    deduplicated: bool
    application_id: Optional[str]
    name: str
    phone: str
    neighborhood: Optional[str]
    campaign_id: Optional[str]
    job_id: Optional[str]
    utm_source: Optional[str]
    utm_medium: Optional[str]
    utm_campaign: Optional[str]
    utm_term: Optional[str]
    utm_content: Optional[str]
    landing_path: Optional[str]
    referrer: Optional[str]
    session_id: Optional[str]
    wa_link_generated: str
    wa_click_count: int
    first_contact_sla_minutes_effective: int
    first_contact_due_utc: datetime
    first_contact_at_utc: Optional[datetime]
    sla_breached: bool
    created_at_utc: datetime
    updated_at_utc: datetime


class WebsiteEventRecord(BaseModel):
    id: str
    event_type: WebsiteEventType
    lead_id: Optional[str]
    campaign_id: Optional[str]
    session_id: Optional[str]
    utm_source: Optional[str]
    utm_medium: Optional[str]
    utm_campaign: Optional[str]
    landing_path: Optional[str]
    referrer: Optional[str]
    metadata: dict[str, Any]
    created_at_utc: datetime
