#!/usr/bin/env bash
# F7 resilience drill: kill the worker mid-scan; SQS redelivers after the visibility timeout,
# the restarted worker finishes, and the scan takes effect exactly once (idempotent by scan_id).
# Needs the compose stack (scripts/dev-up.sh). Usage: scripts/drill-worker-crash.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
DC="docker compose -f local/docker-compose.yml"
API_PY() { (cd api && uv run python ../scripts/drill_api.py "$@"); }
psql_q() { $DC exec -T postgres psql -U dlp -d dlp -tAc "$1"; }

echo "== 1. start a slow worker (20 s scan), queue visibility timeout is 15 s"
SCAN_DELAY_SECONDS=20 $DC up -d --no-deps --force-recreate worker >/dev/null
sleep 4

echo "== 2. send a transfer"
ID=$(API_PY create | tail -1)
echo "transfer id: $ID"

echo "== 3. wait until the worker is mid-scan, then kill -9 it"
for _ in $(seq 1 30); do
  $DC logs worker 2>&1 | grep -q "simulated slow scan" && break
  sleep 1
done
$DC kill -s SIGKILL worker >/dev/null
echo "worker killed at $(date -u +%H:%M:%S) while scanning transfer $ID"
echo "transfer status now: $(psql_q "select status from transfers where id=$ID")"

echo "== 4. restart the worker (no delay); SQS makes the message visible again"
SCAN_DELAY_SECONDS=0 $DC up -d --no-deps --force-recreate worker >/dev/null
STATUS=$(API_PY wait "$ID")
echo "transfer status after recovery: $STATUS"

echo "== 5. evidence"
echo "-- worker log (receive counts, no raw PII):"
$DC logs worker 2>&1 | grep -E "scan received|scan completed" | sed -E 's/"ts":"[^"]+",//'
echo "-- findings rows for this transfer (one row per type, none duplicated):"
psql_q "select f.type, f.count from findings f join files fl on fl.id=f.file_id where fl.transfer_id=$ID order by f.type"
echo "-- scan.completed audit rows for this transfer (exactly 1 expected):"
psql_q "select count(*) from audit_events where transfer_id=$ID and action='scan.completed'"
[ "$STATUS" = "pending_approval" ] && [ "$(psql_q "select count(*) from audit_events where transfer_id=$ID and action='scan.completed'")" = "1" ] \
  && echo "DRILL PASSED" || { echo "DRILL FAILED"; exit 1; }
SCAN_DELAY_SECONDS=2 $DC up -d --no-deps --force-recreate worker >/dev/null
