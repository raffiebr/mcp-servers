#!/usr/bin/env bash
# Run on YOUR laptop once. Creates the shared VM, its static IP and firewall rules.
set -euo pipefail
. "$(dirname "$0")/lib.sh"

gcloud services enable compute.googleapis.com iap.googleapis.com
ensure_vm_sa

# Static IP so DNS and Google OAuth redirect URIs never change.
gcloud compute addresses describe "$VM-ip" >/dev/null 2>&1 || gcloud compute addresses create "$VM-ip"
IP=$(gcloud compute addresses describe "$VM-ip" --format='value(address)')

gcloud compute instances describe "$VM" >/dev/null 2>&1 || \
  gcloud compute instances create "$VM" \
    --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
    --boot-disk-size 20GB --address "$IP" --tags "$VM" \
    --service-account "$VM_SA" --scopes cloud-platform \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring

# Public: 80 (ACME challenge + redirect) and 443. SSH: only via IAP. The deny rule
# outranks the default network's allow-ssh-from-anywhere rule for this VM.
rule() {  # rule <name> <gcloud firewall-rules create flags...>
  gcloud compute firewall-rules describe "$1" >/dev/null 2>&1 || \
    gcloud compute firewall-rules create "$@" --target-tags "$VM"
}
rule "$VM-web" --allow tcp:80,tcp:443 --source-ranges 0.0.0.0/0
rule "$VM-iap-ssh" --allow tcp:22 --source-ranges 35.235.240.0/20 --priority 1000
rule "$VM-deny-ssh" --action deny --rules tcp:22 --source-ranges 0.0.0.0/0 --priority 2000

echo "VM ready at $IP. Point an A record for each *_DOMAIN in deploy/.env at it."
