#!/usr/bin/env bash
# Run on YOUR laptop: SSH into the VM through IAP, or run one command there.
#   bash deploy/ssh.sh
#   bash deploy/ssh.sh 'cd mcp-servers/deploy && sudo docker compose logs -f garmin'
set -euo pipefail
. "$(dirname "$0")/lib.sh"
gcloud compute ssh "$VM" --tunnel-through-iap ${1+"--command=$1"}
