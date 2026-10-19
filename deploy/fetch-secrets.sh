#!/usr/bin/env bash
# Runs ON THE VM (vm-bootstrap.sh calls it). Pulls a server's secrets, as listed in
# deploy/<server>.secrets, into /etc/mcp-servers/<server>.env (root-only, mode 600).
set -euo pipefail
server="${1:?usage: fetch-secrets.sh <server>}"
manifest="$(dirname "$0")/$server.secrets"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
while read -r var _ <&3; do
  case "$var" in ''|\#*) continue ;; esac
  value=$(gcloud secrets versions access latest --secret="$server-mcp-$(printf '%s' "$var" | tr 'A-Z_' 'a-z-')")
  printf '%s=%s\n' "$var" "$value"
done 3< "$manifest" > "$tmp"

sudo install -d -m 700 /etc/mcp-servers
sudo install -m 600 "$tmp" "/etc/mcp-servers/$server.env"
echo "Wrote /etc/mcp-servers/$server.env"
