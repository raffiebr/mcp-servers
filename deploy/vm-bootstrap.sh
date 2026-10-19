#!/usr/bin/env bash
# Runs ON THE VM (deploy.sh calls it). Installs Docker, writes each server's secrets and
# data dir, then builds and starts everything. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl unattended-upgrades   # automatic OS security patches
  curl -fsSL https://get.docker.com | sudo sh
fi

for manifest in *.secrets; do
  server="${manifest%.secrets}"
  # Persistent data dir, owned by the container's non-root uid (10001 in each Dockerfile).
  sudo install -d -m 700 -o 10001 -g 10001 "/var/lib/mcp-servers/$server"
  bash fetch-secrets.sh "$server"
done

sudo docker compose up -d --build --remove-orphans
sudo docker compose ps
