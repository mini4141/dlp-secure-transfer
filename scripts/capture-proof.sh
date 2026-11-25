#!/usr/bin/env bash
# Capture proof for a phase by driving Playwright headless (reproducible, never by hand).
#   scripts/capture-proof.sh phase1   local compose stack (+ kind/ArgoCD if the kind cluster exists)
#   scripts/capture-proof.sh phase2   AWS: needs BASE_URL and SEED_PASSWORD (deploy.sh sets them) and KUBECONFIG
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
ROOT="$(cygpath -m "$(pwd)" 2>/dev/null || pwd)"
PHASE="${1:?usage: capture-proof.sh phase1|phase2}"
DC="docker compose -f local/docker-compose.yml"

redact() { sed -E 's/[0-9]{12}/<ACCOUNT_ID>/g; s/(AKIA|ASIA)[A-Z0-9]{16}/<ACCESS_KEY>/g'; }

argocd_shot() { # $1 shot dir, $2 shot name
  local pw pf
  pw=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)
  kubectl -n argocd port-forward svc/argocd-server 28080:80 >/dev/null 2>&1 &
  pf=$!
  sleep 4
  (cd e2e && ARGOCD_URL=http://localhost:28080 ARGOCD_PASSWORD="$pw" SHOT_DIR="$1" ARGOCD_SHOT_NAME="$2" \
     REPORT_DIR="$ROOT/proof/$3/tests/playwright-argocd" npx playwright test argocd) || { kill $pf; return 1; }
  kill $pf 2>/dev/null || true
}

[ -d e2e/node_modules ] || (cd e2e && npm ci >/dev/null)

if [ "$PHASE" = "phase1" ]; then
  P=proof/phase1-local; mkdir -p $P/{screenshots,logs,tests}
  bash scripts/dev-up.sh >/dev/null

  echo "== screenshots 01-07 + 09 (journey + Jaeger trace)"
  (cd e2e && SHOT_DIR="$ROOT/$P/screenshots" JAEGER_URL=http://localhost:26686 REPORT_DIR="$ROOT/$P/tests/playwright" npx playwright test journey trace)

  echo "== logs"
  $DC logs --no-log-prefix worker 2>&1 | grep '^{' > $P/logs/worker-scan.log
  { echo "raw card numbers in worker log:  $(grep -c '4111 1111 1111 1111\|5555 5555 5555 4444\|3782 822463' $P/logs/worker-scan.log || true)";
    echo "raw emails in worker log:        $(grep -c 'taro.yamada@example.com' $P/logs/worker-scan.log || true)";
    echo "raw card numbers in api log:     $($DC logs --no-log-prefix api 2>&1 | grep -c '4111 1111 1111 1111' || true)"; } > $P/logs/pii-in-logs-check.txt
  $DC logs --no-log-prefix api 2>&1 | grep '^{' | tail -40 > $P/logs/api-structured.log
  { echo "# api"; curl -fsS localhost:18000/metrics | grep -E '^(http_requests_total|dlp_)' | head -25;
    echo "# worker"; curl -fsS localhost:19090/metrics | grep -E '^dlp_worker' | head -15; } > $P/logs/prometheus-metrics.txt
  $DC ps > $P/logs/compose-ps.txt
  bash scripts/drill-worker-crash.sh 2>&1 | tee $P/logs/drill-worker-crash.log >/dev/null

  if kind get clusters 2>/dev/null | grep -qx dlp; then
    echo "== kind + ArgoCD"
    kubectl config use-context kind-dlp >/dev/null
    { kubectl get all -n dlp; echo; kubectl get applications -n argocd; echo; kubectl get pods -n argocd; } > $P/logs/kind-get-all.txt
    (cd e2e && BASE_URL=http://localhost:28000 REPORT_DIR="$ROOT/$P/tests/playwright-kind" npx playwright test journey)
    argocd_shot "$ROOT/$P/screenshots" 08-argocd-app phase1-local
  else
    echo "kind cluster not found: run scripts/kind-up.sh for 08-argocd-app.png and kind-get-all.txt"
  fi

elif [ "$PHASE" = "phase2" ]; then
  : "${BASE_URL:?BASE_URL required}" "${SEED_PASSWORD:?SEED_PASSWORD required}"
  P=proof/phase2-cloud; mkdir -p $P/{screenshots,logs,tests}
  echo "== journey against $BASE_URL (EKS)"
  (cd e2e && BASE_URL="$BASE_URL" SEED_PASSWORD="$SEED_PASSWORD" SHOT_SET=eks SHOT_DIR="$ROOT/$P/screenshots" \
     REPORT_DIR="$ROOT/$P/tests/playwright-eks" npx playwright test journey)
  argocd_shot "$ROOT/$P/screenshots" 04-eks-argocd phase2-cloud
  bash scripts/capture-aws-evidence.sh
else
  echo "unknown phase $PHASE" >&2; exit 2
fi
echo "proof captured under proof/$PHASE*"
