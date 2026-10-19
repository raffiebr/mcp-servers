# mcp-servers

Self-hosted MCP servers for Claude custom connectors. They all run on one small GCE VM
in a personal GCP project: Caddy in front, one container and one subdomain per server.

| Server | What it does |
|---|---|
| [`servers/garmin`](servers/garmin) | Read-only Garmin Connect data for one allowlisted Google account ([design](servers/garmin/DESIGN.md)) |

```
servers/<name>/   a standalone uv project with its own Dockerfile
deploy/           shared by every server: VM, Caddy, compose file, secrets
```

## Personal GCP only

The laptop scripts in `deploy/` run every gcloud command as `GCLOUD_ACCOUNT` against
`PROJECT` from `deploy/.env` (through `CLOUDSDK_CORE_ACCOUNT` / `CLOUDSDK_CORE_PROJECT`),
so your default gcloud config, such as a work account, is neither used nor changed. They
stop if gcloud has no credentials for that account.

## First deploy

1. Log gcloud into your personal account without making it the default:
   `gcloud auth login you@gmail.com --no-activate` (skip if `gcloud auth list` shows it).
2. `cp deploy/.env.example deploy/.env` and fill it in.
3. `bash deploy/provision-vm.sh`, then point an A record for each `*_DOMAIN` at the printed IP.
4. Create each server's Google OAuth client in the personal project's console
   (garmin: see [its design doc](servers/garmin/DESIGN.md#deployment); redirect URIs `https://<GARMIN_DOMAIN>/auth/callback`
   and `https://<GARMIN_DOMAIN>/setup/callback`). Check the console's account switcher shows
   your personal account.
5. `bash deploy/create-secrets.sh garmin`
6. `bash deploy/deploy.sh`
7. `curl https://<GARMIN_DOMAIN>/healthz` returns `ok`.

## Day to day

| Task | Command |
|---|---|
| Ship a code change | `bash deploy/deploy.sh` |
| Change who's allowed | `bash deploy/create-secrets.sh garmin ALLOWED_EMAILS`, then `bash deploy/deploy.sh` |
| Logs | `bash deploy/ssh.sh 'cd mcp-servers/deploy && sudo docker compose logs -f garmin'` |
| Shell on the VM | `bash deploy/ssh.sh` |

Server state lives on the VM in `/var/lib/mcp-servers/<name>`, and secrets in
`/etc/mcp-servers/<name>.env`; `deploy.sh` replaces only the code in `~/mcp-servers`.

## Who can use the Garmin server

One deployment serves one person: one allowlist and one connected Garmin account. Anyone
on `ALLOWED_EMAILS` can read whichever Garmin account is connected, so never list two
people at once.

- **Hand it to someone else:** the current person clicks Disconnect Garmin on `/setup`,
  then run `bash deploy/create-secrets.sh garmin ALLOWED_EMAILS` with only the new email,
  then `bash deploy/deploy.sh`.
- **A second person with their own Garmin:** run a second copy, e.g. a `garmin-alex`
  service built from `servers/garmin`, with its own `garmin-alex.secrets`, data dir and
  subdomain (steps below). The same Google OAuth client can serve it once you add the new
  subdomain's two redirect URIs.

## Adding a server

1. `servers/<name>/` with a Dockerfile that serves on port 8000 as uid 10001 and keeps
   state in `/data`. Containers can reach the VM's metadata server, whose token reads
   every server's secrets, so add only code you trust as much as the existing servers.
2. `deploy/<name>.secrets` listing its secrets (an empty file if it has none).
3. A `<name>` service in `deploy/docker-compose.yml`, and its `<NAME>_DOMAIN` in the
   caddy service's environment.
4. `{$<NAME>_DOMAIN} { import mcp_server <name>:8000 }` in `deploy/Caddyfile`.
5. `<NAME>_DOMAIN` in `deploy/.env` and `.env.example`, plus an A record for it.
6. `bash deploy/create-secrets.sh <name>`, then `bash deploy/deploy.sh`.
