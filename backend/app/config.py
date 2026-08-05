from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, cleaned)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if raw is None:
        return default
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return items or default


_load_local_env()


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Growth Gap Strategy API")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "admin123")
    session_ttl_minutes: int = _env_int("SESSION_TTL_MINUTES", 480)
    google_oauth_enabled: bool = _env_bool("GOOGLE_OAUTH_ENABLED", False)
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/auth/google/callback",
    )
    oauth_state_ttl_minutes: int = _env_int("OAUTH_STATE_TTL_MINUTES", 10)
    scraper_min_delay_seconds: float = _env_float("SCRAPER_MIN_DELAY_SECONDS", 1.2)
    scraper_max_delay_seconds: float = _env_float("SCRAPER_MAX_DELAY_SECONDS", 2.2)
    scraper_retry_max_attempts: int = _env_int("SCRAPER_RETRY_MAX_ATTEMPTS", 3)
    scraper_backoff_base_seconds: float = _env_float("SCRAPER_BACKOFF_BASE_SECONDS", 15.0)
    scraper_backoff_max_seconds: float = _env_float("SCRAPER_BACKOFF_MAX_SECONDS", 180.0)
    scraper_backoff_jitter_seconds: float = _env_float("SCRAPER_BACKOFF_JITTER_SECONDS", 1.5)
    cors_origins: list[str] = _env_list(
        "CORS_ORIGINS",
        [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        ],
    )


settings = Settings()
