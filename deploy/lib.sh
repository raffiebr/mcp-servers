# Sourced by the laptop scripts. Loads deploy/.env and runs every gcloud command as
# your personal account and project, whatever your default gcloud config points at.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "$ROOT/deploy/.env" ]; then
  echo "Missing deploy/.env: copy deploy/.env.example and fill it in." >&2
  exit 1
fi
set -a; . "$ROOT/deploy/.env"; set +a
: "${GCLOUD_ACCOUNT:?set in deploy/.env}" "${PROJECT:?set in deploy/.env}"
: "${REGION:?set in deploy/.env}" "${ZONE:?set in deploy/.env}" "${VM:?set in deploy/.env}"

export CLOUDSDK_CORE_ACCOUNT="$GCLOUD_ACCOUNT" CLOUDSDK_CORE_PROJECT="$PROJECT" \
  CLOUDSDK_COMPUTE_REGION="$REGION" CLOUDSDK_COMPUTE_ZONE="$ZONE"
if [ -z "$(gcloud auth list --filter-account="$GCLOUD_ACCOUNT" --format='value(account)')" ]; then
  echo "gcloud has no credentials for $GCLOUD_ACCOUNT. Run: gcloud auth login $GCLOUD_ACCOUNT --no-activate" >&2
  exit 1
fi

# The VM's identity. It can read only the secrets create-secrets.sh grants it.
VM_SA="$VM-vm@$PROJECT.iam.gserviceaccount.com"
ensure_vm_sa() {
  gcloud iam service-accounts describe "$VM_SA" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "$VM-vm" --display-name "$VM VM"
}
