"""Settings, loaded once from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    base_url: str                   # public HTTPS origin, e.g. https://garmin.example.com
    google_client_id: str
    google_client_secret: str
    allowed_emails: frozenset[str]  # Google accounts allowed to use the connector
    jwt_signing_key: str            # signs the tokens FastMCP issues to Claude
    storage_encryption_key: str     # Fernet key for OAuth client storage at rest
    session_secret: str             # signs the /setup page session cookie
    data_dir: str                   # persistent volume (OAuth store + Garmin tokens)
    timezone: str                   # used to resolve "today" for date defaults
    port: int

    @property
    def garmin_token_dir(self) -> str:
        return os.path.join(self.data_dir, "garmin")

    @property
    def oauth_store_dir(self) -> str:
        return os.path.join(self.data_dir, "oauth")

    @property
    def is_https(self) -> bool:
        return self.base_url.startswith("https://")


def load_settings() -> Settings:
    emails = frozenset(
        e.strip().lower() for e in _required("ALLOWED_EMAILS").split(",") if e.strip()
    )
    if not emails:
        raise RuntimeError("ALLOWED_EMAILS must list at least one Google account")
    return Settings(
        base_url=_required("BASE_URL").rstrip("/"),
        google_client_id=_required("GOOGLE_CLIENT_ID"),
        google_client_secret=_required("GOOGLE_CLIENT_SECRET"),
        allowed_emails=emails,
        jwt_signing_key=_required("JWT_SIGNING_KEY"),
        storage_encryption_key=_required("STORAGE_ENCRYPTION_KEY"),
        session_secret=_required("SESSION_SECRET"),
        data_dir=os.environ.get("DATA_DIR", "/data"),
        timezone=os.environ.get("TIMEZONE", "Asia/Singapore"),
        port=int(os.environ.get("PORT", "8000")),
    )
