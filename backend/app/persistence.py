from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.app.models import (
    Coordinates,
    Language,
    ManualLeadRecord,
    SourceChannel,
    WebhookDeliveryRecord,
    WebhookProcessingStatus,
)


def _dt_to_text(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _text_to_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _normalize_database_url(database_url: str) -> str:
    value = database_url.strip()
    if value.startswith("sqlite:///"):
        sqlite_path = value[len("sqlite:///") :].split("?", 1)[0]
        if sqlite_path and sqlite_path != ":memory:":
            path = Path(sqlite_path)
            if path.parent:
                path.parent.mkdir(parents=True, exist_ok=True)
        return value
    if "://" in value:
        return value
    path = Path(value)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{str(path).replace(chr(92), '/')}"


class SqlitePersistence:
    """
    Backward-compatible name. Uses SQLAlchemy and supports both SQLite and PostgreSQL URLs.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = _normalize_database_url(database_url)
        self._lock = Lock()
        self.engine: Engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
        )
        self.metadata = MetaData()
        self.state_snapshots = Table(
            "state_snapshots",
            self.metadata,
            Column("id", String(50), primary_key=True),
            Column("payload_json", Text, nullable=False),
            Column("updated_at_utc", DateTime, nullable=False),
        )
        self.webhook_deliveries = Table(
            "webhook_deliveries",
            self.metadata,
            Column("key", String(255), primary_key=True),
            Column("id", String(255), nullable=False),
            Column("channel", String(50), nullable=False),
            Column("event_id", String(255), nullable=False),
            Column("status", String(50), nullable=False),
            Column("attempts", Integer, nullable=False),
            Column("last_error", Text, nullable=True),
            Column("next_retry_utc", DateTime, nullable=True),
            Column("created_at_utc", DateTime, nullable=False),
            Column("updated_at_utc", DateTime, nullable=False),
        )
        self.manual_leads = Table(
            "manual_leads",
            self.metadata,
            Column("id", String(255), primary_key=True),
            Column("source_channel", String(50), nullable=False),
            Column("name", String(120), nullable=False),
            Column("phone", String(20), nullable=False),
            Column("languages_json", Text, nullable=False),
            Column("therapy_experience_json", Text, nullable=False),
            Column("experience_years", Float, nullable=False),
            Column("certifications_json", Text, nullable=False),
            Column("expected_pay", Integer, nullable=True),
            Column("current_location_json", Text, nullable=True),
            Column("preferred_shift_start", String(20), nullable=True),
            Column("preferred_shift_end", String(20), nullable=True),
            Column("referred_by", String(120), nullable=True),
            Column("last_employer", String(120), nullable=True),
            Column("job_id", String(120), nullable=True),
            Column("neighborhood", String(120), nullable=True),
            Column("notes", Text, nullable=True),
            Column("created_by", String(120), nullable=True),
            Column("candidate_id", String(120), nullable=False),
            Column("deduplicated", Integer, nullable=False),
            Column("application_id", String(120), nullable=True),
            Column("created_at_utc", DateTime, nullable=False),
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.metadata.create_all(self.engine)

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(select(1))
            return True
        except SQLAlchemyError:
            return False

    def save_snapshot(self, payload: dict) -> None:
        with self._lock:
            serialized = json.dumps(payload)
            now = datetime.utcnow()
            with self.engine.begin() as conn:
                existing = conn.execute(
                    select(self.state_snapshots.c.id).where(self.state_snapshots.c.id == "default")
                ).first()
                if existing:
                    conn.execute(
                        self.state_snapshots.update()
                        .where(self.state_snapshots.c.id == "default")
                        .values(payload_json=serialized, updated_at_utc=now)
                    )
                else:
                    conn.execute(
                        self.state_snapshots.insert().values(
                            id="default",
                            payload_json=serialized,
                            updated_at_utc=now,
                        )
                    )

    def load_snapshot(self) -> Optional[dict]:
        with self._lock:
            with self.engine.connect() as conn:
                row = conn.execute(
                    select(self.state_snapshots.c.payload_json).where(
                        self.state_snapshots.c.id == "default"
                    )
                ).first()
            if not row:
                return None
            return json.loads(row[0])

    def upsert_webhook_delivery(self, record: WebhookDeliveryRecord) -> None:
        with self._lock:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    select(self.webhook_deliveries.c.key).where(
                        self.webhook_deliveries.c.key == record.key
                    )
                ).first()
                payload = {
                    "id": record.id,
                    "channel": record.channel,
                    "event_id": record.event_id,
                    "status": record.status.value,
                    "attempts": record.attempts,
                    "last_error": record.last_error,
                    "next_retry_utc": record.next_retry_utc,
                    "created_at_utc": record.created_at_utc,
                    "updated_at_utc": record.updated_at_utc,
                }
                if existing:
                    conn.execute(
                        self.webhook_deliveries.update()
                        .where(self.webhook_deliveries.c.key == record.key)
                        .values(**payload)
                    )
                else:
                    conn.execute(
                        self.webhook_deliveries.insert().values(key=record.key, **payload)
                    )

    def list_webhook_deliveries(self) -> list[WebhookDeliveryRecord]:
        with self._lock:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    select(
                        self.webhook_deliveries.c.key,
                        self.webhook_deliveries.c.id,
                        self.webhook_deliveries.c.channel,
                        self.webhook_deliveries.c.event_id,
                        self.webhook_deliveries.c.status,
                        self.webhook_deliveries.c.attempts,
                        self.webhook_deliveries.c.last_error,
                        self.webhook_deliveries.c.next_retry_utc,
                        self.webhook_deliveries.c.created_at_utc,
                        self.webhook_deliveries.c.updated_at_utc,
                    )
                ).all()
        output: list[WebhookDeliveryRecord] = []
        for row in rows:
            output.append(
                WebhookDeliveryRecord(
                    key=row.key,
                    id=row.id,
                    channel=row.channel,
                    event_id=row.event_id,
                    status=WebhookProcessingStatus(row.status),
                    attempts=row.attempts,
                    last_error=row.last_error,
                    next_retry_utc=row.next_retry_utc,
                    created_at_utc=row.created_at_utc or datetime.utcnow(),
                    updated_at_utc=row.updated_at_utc or datetime.utcnow(),
                )
            )
        return output

    def insert_manual_lead(self, record: ManualLeadRecord) -> None:
        with self._lock:
            payload = {
                "source_channel": record.source_channel.value,
                "name": record.name,
                "phone": record.phone,
                "languages_json": json.dumps([language.value for language in record.languages]),
                "therapy_experience_json": json.dumps(record.therapy_experience),
                "experience_years": record.experience_years,
                "certifications_json": json.dumps(record.certifications),
                "expected_pay": record.expected_pay,
                "current_location_json": (
                    json.dumps(record.current_location.model_dump())
                    if record.current_location
                    else None
                ),
                "preferred_shift_start": record.preferred_shift_start,
                "preferred_shift_end": record.preferred_shift_end,
                "referred_by": record.referred_by,
                "last_employer": record.last_employer,
                "job_id": record.job_id,
                "neighborhood": record.neighborhood,
                "notes": record.notes,
                "created_by": record.created_by,
                "candidate_id": record.candidate_id,
                "deduplicated": 1 if record.deduplicated else 0,
                "application_id": record.application_id,
                "created_at_utc": record.created_at_utc,
            }
            with self.engine.begin() as conn:
                existing = conn.execute(
                    select(self.manual_leads.c.id).where(self.manual_leads.c.id == record.id)
                ).first()
                if existing:
                    conn.execute(
                        self.manual_leads.update()
                        .where(self.manual_leads.c.id == record.id)
                        .values(**payload)
                    )
                else:
                    conn.execute(self.manual_leads.insert().values(id=record.id, **payload))

    def list_manual_leads(self, limit: int = 100) -> list[ManualLeadRecord]:
        safe_limit = max(1, min(limit, 500))
        with self._lock:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    select(
                        self.manual_leads.c.id,
                        self.manual_leads.c.source_channel,
                        self.manual_leads.c.name,
                        self.manual_leads.c.phone,
                        self.manual_leads.c.languages_json,
                        self.manual_leads.c.therapy_experience_json,
                        self.manual_leads.c.experience_years,
                        self.manual_leads.c.certifications_json,
                        self.manual_leads.c.expected_pay,
                        self.manual_leads.c.current_location_json,
                        self.manual_leads.c.preferred_shift_start,
                        self.manual_leads.c.preferred_shift_end,
                        self.manual_leads.c.referred_by,
                        self.manual_leads.c.last_employer,
                        self.manual_leads.c.job_id,
                        self.manual_leads.c.neighborhood,
                        self.manual_leads.c.notes,
                        self.manual_leads.c.created_by,
                        self.manual_leads.c.candidate_id,
                        self.manual_leads.c.deduplicated,
                        self.manual_leads.c.application_id,
                        self.manual_leads.c.created_at_utc,
                    )
                    .order_by(self.manual_leads.c.created_at_utc.desc())
                    .limit(safe_limit)
                ).all()

        output: list[ManualLeadRecord] = []
        allowed_languages = {language.value for language in Language}
        for row in rows:
            languages = [
                Language(value)
                for value in json.loads(row.languages_json)
                if value in allowed_languages
            ]
            location = (
                Coordinates.model_validate(json.loads(row.current_location_json))
                if row.current_location_json
                else None
            )
            output.append(
                ManualLeadRecord(
                    id=row.id,
                    source_channel=SourceChannel(row.source_channel),
                    name=row.name,
                    phone=row.phone,
                    languages=languages,
                    therapy_experience=json.loads(row.therapy_experience_json),
                    experience_years=float(row.experience_years),
                    certifications=json.loads(row.certifications_json),
                    expected_pay=row.expected_pay,
                    current_location=location,
                    preferred_shift_start=row.preferred_shift_start,
                    preferred_shift_end=row.preferred_shift_end,
                    referred_by=row.referred_by,
                    last_employer=row.last_employer,
                    job_id=row.job_id,
                    neighborhood=row.neighborhood,
                    notes=row.notes,
                    created_by=row.created_by,
                    candidate_id=row.candidate_id,
                    deduplicated=bool(row.deduplicated),
                    application_id=row.application_id,
                    created_at_utc=row.created_at_utc or datetime.utcnow(),
                )
            )
        return output
