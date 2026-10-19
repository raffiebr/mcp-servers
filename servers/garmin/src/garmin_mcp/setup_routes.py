"""The /setup page: Google sign-in, then a form where the owner logs into Garmin.

Protected by its own Google sign-in (Authlib) because FastMCP's auth only
guards the /mcp endpoint. The same email allowlist applies.
"""

from __future__ import annotations

import html
import secrets

import anyio
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .config import Settings
from .garmin_client import GarminManager, LoginSession

STYLE = """
:root{--ink:#14232b;--muted:#5b6b73;--line:#d5dde0;--bg:#f3f6f6;--card:#fff;--accent:#0b6e69;--bad:#a8322d}
@media (prefers-color-scheme:dark){:root{--ink:#e4ecee;--muted:#9aabb2;--line:#2c3b42;--bg:#0f191e;--card:#16232a;--accent:#4fb3ac;--bad:#e2726b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Atkinson Hyperlegible",system-ui,sans-serif}
main{max-width:30rem;margin:8vh auto;padding:2rem;background:var(--card);border:1px solid var(--line);border-radius:14px}
h1{font-size:1.5rem;line-height:1.25;margin:0 0 .75rem}p{margin:.5rem 0 1rem;color:var(--muted)}
label{display:block;font-weight:700;margin:1rem 0 .3rem}input{width:100%;padding:.7rem .8rem;font:inherit;color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:8px}
input:focus,button:focus,a:focus{outline:3px solid var(--accent);outline-offset:2px}
button,.btn{display:inline-block;margin-top:1.25rem;padding:.7rem 1.1rem;font:inherit;font-weight:700;color:#fff;background:var(--accent);border:0;border-radius:8px;cursor:pointer;text-decoration:none}
.quiet{background:transparent;color:var(--accent);border:1px solid var(--line)}.err{color:var(--bad);font-weight:700}
.ok{display:inline-block;padding:.15rem .6rem;border-radius:99px;background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent);font-weight:700}
small{color:var(--muted)}form.inline{display:inline}
"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>{STYLE}</style></head><body><main>{body}</main></body></html>"""
    return HTMLResponse(doc, status_code=status, headers={"Cache-Control": "no-store"})


def register_setup_routes(mcp: FastMCP, garmin: GarminManager, settings: Settings) -> None:
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email", "prompt": "select_account"},
    )
    state: dict[str, LoginSession | None] = {"login": None}

    def signed_in(request: Request) -> str | None:
        email = request.session.get("email")
        return email if email in settings.allowed_emails else None

    def csrf(request: Request) -> str:
        if "csrf" not in request.session:
            request.session["csrf"] = secrets.token_urlsafe(24)
        return request.session["csrf"]

    async def check_post(request: Request) -> dict | Response:
        if not signed_in(request):
            return RedirectResponse("/setup", status_code=303)
        form = dict(await request.form())
        if not secrets.compare_digest(str(form.get("csrf", "")), request.session.get("csrf", "")):
            return _page("Expired", "<h1>That form expired</h1><p>Reload the page and try again.</p><a class='btn' href='/setup'>Reload</a>", 400)
        return form

    def connect_form(request: Request, error: str | None = None) -> HTMLResponse:
        err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
        return _page("Connect Garmin", f"""
<h1>Connect your Garmin account</h1>
<p>Sign in with the email and password you use for the Garmin Connect app. Your password is sent to Garmin once and isn't stored here.</p>{err}
<form method="post" action="/setup/garmin" autocomplete="on">
<input type="hidden" name="csrf" value="{csrf(request)}">
<label for="email">Garmin email</label><input id="email" name="email" type="email" autocomplete="username" required>
<label for="password">Garmin password</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Connect Garmin</button></form>""")

    def mfa_form(request: Request, error: str | None = None) -> HTMLResponse:
        err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
        return _page("Verification code", f"""
<h1>Enter your Garmin verification code</h1>
<p>Garmin just sent a code to your email or phone. It expires in a few minutes.</p>{err}
<form method="post" action="/setup/mfa"><input type="hidden" name="csrf" value="{csrf(request)}">
<label for="code">Verification code</label><input id="code" name="code" inputmode="numeric" autocomplete="one-time-code" required autofocus>
<button type="submit">Verify</button></form>""")

    def connected_page(request: Request) -> HTMLResponse:
        return _page("Garmin connected", f"""
<h1>Garmin is connected <span class="ok">Connected</span></h1>
<p>You can close this page. In Claude, add this connector URL under Settings, Connectors:</p>
<p><strong>{html.escape(settings.base_url)}/mcp</strong></p>
<form class="inline" method="post" action="/setup/disconnect"><input type="hidden" name="csrf" value="{csrf(request)}">
<button class="quiet" type="submit">Disconnect Garmin</button></form>
<p><small>Signed in as {html.escape(request.session.get('email', ''))}. <a href="/setup/logout">Sign out</a></small></p>""")

    def render_login_state(request: Request, session: LoginSession) -> HTMLResponse:
        if session.state == "done":
            state["login"] = None
            return connected_page(request)
        if session.state == "needs_mfa":
            return mfa_form(request)
        if session.state == "error":
            state["login"] = None
            return connect_form(request, session.error)
        return _page("Still working", "<h1>Still talking to Garmin</h1><p>This can take up to a minute.</p><a class='btn' href='/setup'>Check again</a>")

    @mcp.custom_route("/setup", methods=["GET"])
    async def setup_home(request: Request) -> Response:
        if not signed_in(request):
            return _page("Garmin for Claude", """
<h1>Garmin for Claude</h1><p>First, sign in with the Google account you use for Claude so this server knows it's you.</p>
<a class="btn" href="/setup/login">Sign in with Google</a>""")
        session = state["login"]
        if session and session.state in ("running", "needs_mfa"):
            return render_login_state(request, session)
        return connected_page(request) if garmin.has_tokens() else connect_form(request)

    @mcp.custom_route("/setup/login", methods=["GET"])
    async def setup_login(request: Request) -> Response:
        return await oauth.google.authorize_redirect(request, f"{settings.base_url}/setup/callback")

    @mcp.custom_route("/setup/callback", methods=["GET"])
    async def setup_callback(request: Request) -> Response:
        try:
            token = await oauth.google.authorize_access_token(request)
        except OAuthError:
            return _page("Sign-in failed", "<h1>Google sign-in didn't finish</h1><a class='btn' href='/setup/login'>Try again</a>", 400)
        info = token.get("userinfo") or {}
        email = str(info.get("email", "")).lower()
        if not info.get("email_verified") or email not in settings.allowed_emails:
            request.session.clear()
            return _page("Not allowed", f"<h1>This Google account isn't allowed</h1><p>{html.escape(email)} isn't on this server's list. Sign in with the account you use for Claude.</p><a class='btn' href='/setup/login'>Use another account</a>", 403)
        request.session["email"] = email
        return RedirectResponse("/setup", status_code=303)

    @mcp.custom_route("/setup/garmin", methods=["POST"])
    async def setup_garmin(request: Request) -> Response:
        form = await check_post(request)
        if isinstance(form, Response):
            return form
        session = LoginSession(garmin, str(form.get("email", "")).strip(), str(form.get("password", "")))
        del form
        state["login"] = session
        await anyio.to_thread.run_sync(session.wait_until_settled, 45)
        return render_login_state(request, session)

    @mcp.custom_route("/setup/mfa", methods=["POST"])
    async def setup_mfa(request: Request) -> Response:
        form = await check_post(request)
        if isinstance(form, Response):
            return form
        session = state["login"]
        if not session or session.state != "needs_mfa":
            return connect_form(request, "That code arrived too late. Start again.")
        session.submit_mfa(str(form.get("code", "")))
        await anyio.to_thread.run_sync(session.wait_until_settled, 45)
        return render_login_state(request, session)

    @mcp.custom_route("/setup/disconnect", methods=["POST"])
    async def setup_disconnect(request: Request) -> Response:
        form = await check_post(request)
        if isinstance(form, Response):
            return form
        garmin.disconnect()
        return connect_form(request)

    @mcp.custom_route("/setup/logout", methods=["GET"])
    async def setup_logout(request: Request) -> Response:
        request.session.clear()
        return RedirectResponse("/setup", status_code=303)

    # Linked from the Google OAuth consent screen, which needs a privacy policy to publish.
    @mcp.custom_route("/privacy", methods=["GET"])
    async def privacy(_: Request) -> Response:
        return _page("Privacy", """
<h1>Privacy</h1>
<p>Garmin for Claude is a private server that lets one person's Claude account read their own Garmin Connect data. Only the Google account on its allowlist can use it.</p>
<p><strong>What it reads.</strong> Your Google email address, to check it's you, and your Garmin data, only when Claude asks for it. It can't change anything in your Garmin account.</p>
<p><strong>What it keeps.</strong> Garmin's sign-in pass and Claude's connection details, on a Google Cloud server in Singapore. Your Garmin password and your health data aren't stored or logged.</p>
<p><strong>Who sees it.</strong> Your data goes only to your Claude account. The person who runs this server can technically access the stored sign-in pass.</p>
<p><strong>How to stop.</strong> Remove the connector in Claude's settings, then click Disconnect Garmin on the <a href="/setup">setup page</a>. That deletes the stored sign-in pass.</p>
<p><small>Questions go to the person who set this up for you.</small></p>""")

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> Response:
        return Response("ok", media_type="text/plain")
