#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f local/docker-compose.yml down -v --remove-orphans
