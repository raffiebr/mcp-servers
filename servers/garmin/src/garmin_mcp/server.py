"""Wiring: Google OAuth for Claude, email allowlist, tools, setup page, HTTP app."""

from __future__ import annotations

import logging
import os

import uvicorn
from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext
from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, load_settings
from .garmin_client import GarminManager
from .setup_routes import register_setup_routes
from .tools import register_tools

log = logging.getLogger("garmin_mcp")

INSTRUCTIONS = """Read-only access to the user's Garmin Connect data: sleep, HRV, stress,
Body Battery, heart rate, training readiness and status, VO2 max, race predictions,
body composition and activities. Dates are ISO YYYY-MM-DD in the user's timezone.
Call garmin_status first if unsure whether Garmin is connected. Prefer the specific
tools; use query_garmin only for data they don't cover."""


class AllowlistMiddleware(Middleware):
    """Google OAuth proves who the caller is; this decides whether they may use the server."""

    def __init__(self, allowed: frozenset[str]) -> None:
        self.allowed = allowed

    def _check(self) -> None:
        token = get_access_token()
        email = str((token.claims or {}).get("email", "")).lower() if token else ""
        if email not in self.allowed:
            log.warning("Refused MCP request from %r", email or "<no token>")
            raise ToolError("This Google account isn't allowed to use this Garmin connector.")

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        self._check()
        return await call_next(context)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        self._check()
        return await call_next(context)


def build_app(settings: Settings):
    os.makedirs(settings.oauth_store_dir, mode=0o700, exist_ok=True)

    auth = GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        base_url=settings.base_url,
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
        # Persist Claude's client registration + issued tokens across restarts,
        # encrypted at rest, so she isn't asked to reconnect after every deploy.
        jwt_signing_key=settings.jwt_signing_key,
        client_storage=FernetEncryptionWrapper(
            key_value=DiskStore(directory=settings.oauth_store_dir),
            fernet=Fernet(settings.storage_encryption_key),
        ),
    )

    mcp = FastMCP(name="Garmin", instructions=INSTRUCTIONS, auth=auth)
    mcp.add_middleware(AllowlistMiddleware(settings.allowed_emails))

    garmin = GarminManager(settings.garmin_token_dir)
    register_tools(mcp, garmin, settings)
    register_setup_routes(mcp, garmin, settings)

    app = mcp.http_app(path="/mcp")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="garmin_setup",
        max_age=60 * 60,
        same_site="lax",
        https_only=settings.is_https,
    )
    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    settings = load_settings()
    uvicorn.run(
        build_app(settings),
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",  # only Caddy can reach the app port
    )


if __name__ == "__main__":
    main()
