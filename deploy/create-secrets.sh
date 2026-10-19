#!/usr/bin/env bash
# Run on YOUR laptop. Creates a server's missing secrets (listed in deploy/<server>.secrets)
# in Secret Manager and lets the VM read them. Existing secrets are kept unless named.
#   bash deploy/create-secrets.sh garmin                  # first time
#   bash deploy/create-secrets.sh garmin ALLOWED_EMAILS   # replace one value
set -euo pipefail
. "$(dirname "$0")/lib.sh"
server="${1:?usage: create-secrets.sh <server> [ENV_VAR]}"
only="${2:-}"
manifest="$ROOT/deploy/$server.secrets"

new_value() {  # new_value <ENV_VAR> <source>; prompts go to stderr, the value to stdout
  local value
  case "$2" in
    ask)        read -rp "$1: " value ;;
    ask-hidden) read -rsp "$1: " value; echo >&2 ;;
    random)     value=$(openssl rand -base64 48) ;;
    fernet)     value=$(openssl rand 32 | base64 | tr '+/' '-_') ;;
    *) echo "$manifest: unknown source '$2' for $1" >&2; return 1 ;;
  esac
  [ -n "$value" ] || { echo "$1 can't be empty" >&2; return 1; }
  printf '%s' "$value"
}

gcloud services enable secretmanager.googleapis.com
ensure_vm_sa

found=
while read -r var source <&3; do
  case "$var" in ''|\#*) continue ;; esac
  [ -z "$only" ] || [ "$var" = "$only" ] || continue
  found=1
  name="$server-mcp-$(printf '%s' "$var" | tr 'A-Z_' 'a-z-')"
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    value=$(new_value "$var" "$source")
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --replication-policy=automatic
  elif [ -n "$only" ]; then
    value=$(new_value "$var" "$source")
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=-
  else
    echo "$name exists, kept"
  fi
  gcloud secrets add-iam-policy-binding "$name" --member "serviceAccount:$VM_SA" \
    --role roles/secretmanager.secretAccessor >/dev/null
done 3< "$manifest"

[ -n "$found" ] || { echo "$only isn't listed in $manifest" >&2; exit 1; }
echo "Done. Run deploy/deploy.sh to push the values to the VM."
