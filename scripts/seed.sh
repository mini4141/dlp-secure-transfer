#!/usr/bin/env bash
# Load demo users (sam/ava/admin). The API also seeds on start when SEED_ON_START=true.
# Usage: scripts/seed.sh            -> docker compose stack
#        scripts/seed.sh k8s [ns]   -> run inside the API deployment
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
if [ "${1:-}" = "k8s" ]; then
  kubectl -n "${2:-dlp}" exec deploy/dlp-secure-transfer-api -- python -m app.seed
else
  docker compose -f local/docker-compose.yml exec -T api python -m app.seed
fi
