#!/usr/bin/env bash
# Run on YOUR laptop, for the first deploy and every update: copies the repo to the VM,
# then runs vm-bootstrap.sh there. Safe to re-run.
set -euo pipefail
. "$(dirname "$0")/lib.sh"

tarball=$(mktemp)
trap 'rm -f "$tarball"' EXIT
# Source only: no venvs, caches, or the servers' local .env files and data dirs.
COPYFILE_DISABLE=1 tar -czf "$tarball" -C "$ROOT" --no-mac-metadata \
  --exclude .git --exclude .venv --exclude __pycache__ --exclude .DS_Store \
  --exclude 'servers/*/.env' --exclude 'servers/*/data' .

gcloud compute scp --tunnel-through-iap "$tarball" "$VM:mcp-servers.tgz"
gcloud compute ssh "$VM" --tunnel-through-iap --command \
  'rm -rf mcp-servers && mkdir mcp-servers && tar -xzf mcp-servers.tgz -C mcp-servers && rm mcp-servers.tgz && bash mcp-servers/deploy/vm-bootstrap.sh'
