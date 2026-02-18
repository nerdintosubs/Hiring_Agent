from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    persistence_enabled: bool
    persistence_db_path: str
    database_url: str
    whatsapp_webhook_secret: str
    telephony_webhook_secret: str
    webhook_max_retries: int
    webhook_retry_backoff_seconds: int
    auth_enabled: bool
    jwt_secret: str
    jwt_algorithm: str
    default_first_contact_sla_minutes: int
    website_whatsapp_number: str


def load_settings() -> Settings:
    persistence_db_path = os.getenv("PERSISTENCE_DB_PATH", "data/hiring_agent.sqlite3").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        database_url = f"sqlite:///{persistence_db_path.replace(chr(92), '/')}"
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        persistence_enabled=_bool_env("PERSISTENCE_ENABLED", True),
        persistence_db_path=persistence_db_path,
        database_url=database_url,
        whatsapp_webhook_secret=os.getenv("WHATSAPP_WEBHOOK_SECRET", "").strip(),
        telephony_webhook_secret=os.getenv("TELEPHONY_WEBHOOK_SECRET", "").strip(),
        webhook_max_retries=max(1, _int_env("WEBHOOK_MAX_RETRIES", 3)),
        webhook_retry_backoff_seconds=max(1, _int_env("WEBHOOK_RETRY_BACKOFF_SECONDS", 60)),
        auth_enabled=_bool_env("AUTH_ENABLED", False),
        jwt_secret=os.getenv("JWT_SECRET", "dev-only-secret-change-in-prod").strip(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256").strip(),
        default_first_contact_sla_minutes=max(
            5, min(240, _int_env("DEFAULT_FIRST_CONTACT_SLA_MINUTES", 30))
        ),
        website_whatsapp_number=os.getenv("WEBSITE_WHATSAPP_NUMBER", "+919187351205").strip(),
    )
