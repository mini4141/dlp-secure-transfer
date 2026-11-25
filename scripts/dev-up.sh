#!/usr/bin/env bash
# Start the full local stack (postgres, moto S3/SQS, jaeger, migrations, api, worker).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
docker compose -f local/docker-compose.yml up -d --build --wait "$@"
echo "API:    http://localhost:18000   (sam@corp.test / ava@corp.test / admin@corp.test, password: demo-password)"
echo "Jaeger: http://localhost:26686"
