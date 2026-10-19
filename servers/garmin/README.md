# garmin-mcp

Single-user, self-hosted Garmin Connect MCP server for a Claude custom connector.

- `/mcp` — the MCP endpoint Claude connects to (Google OAuth + email allowlist)
- `/setup` — page where the Garmin owner signs in with Google, then logs into Garmin once
- `/privacy` — privacy policy, linked from the Google OAuth consent screen
- `/healthz` — liveness check

Design, deployment, security model and handover checklist: [DESIGN.md](DESIGN.md).
Guide for the person being connected: [Using Garmin with Claude](https://claude.ai/artifact/MydTugv1s4XXwhedWk4Ems).

## Quick start (local)

```bash
cp .env.example .env              # fill in values
uv run --env-file .env garmin-mcp # http://localhost:8000/setup
```

## Deploy

Deployed with the other servers in this repo from the shared `../../deploy/` (see the
repo README). Its secrets are listed in `../../deploy/garmin.secrets`.

Smoke test against a deployment:

```bash
uv run python scripts/smoke_test.py https://garmin.example.com
```
