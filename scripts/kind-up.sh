#!/usr/bin/env bash
# Prove the Kubernetes path locally: kind + ArgoCD watching this public repo, chart values-kind.yaml.
# postgres and moto run in-cluster. App: http://localhost:28000
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
CLUSTER=dlp
ARGOCD_CHART_VERSION="${ARGOCD_CHART_VERSION:-10.19.1}"

if [ "$(git rev-parse HEAD)" != "$(git ls-remote origin refs/heads/main | cut -f1)" ]; then
  echo "WARNING: local HEAD differs from origin/main. ArgoCD syncs from GitHub, so push first." >&2
fi

kind get clusters | grep -qx "$CLUSTER" || kind create cluster --config local/kind-config.yaml --wait 120s

echo "== build + load images"
docker build -q -t dlp-api:dev api >/dev/null
docker build -q -t dlp-worker:dev worker >/dev/null
kind load docker-image dlp-api:dev dlp-worker:dev --name "$CLUSTER"

echo "== install ArgoCD (official argo-cd chart)"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo update argo >/dev/null
helm upgrade --install argocd argo/argo-cd --version "$ARGOCD_CHART_VERSION" -n argocd --create-namespace \
  --set dex.enabled=false --set notifications.enabled=false --set applicationSet.enabled=false \
  --set-string 'configs.params.server\.insecure=true' --wait --timeout 8m

echo "== create the Application (deploy/helm, values-kind.yaml)"
bash scripts/render-app.sh values-kind.yaml | kubectl apply -f -
kubectl -n argocd wait application/dlp-secure-transfer --for=jsonpath='{.status.sync.status}'=Synced --timeout=600s
kubectl -n argocd wait application/dlp-secure-transfer --for=jsonpath='{.status.health.status}'=Healthy --timeout=600s
kubectl -n dlp rollout status deploy/dlp-secure-transfer-api --timeout=300s
echo "kind stack ready: http://localhost:28000 (ArgoCD: kubectl -n argocd port-forward svc/argocd-server 28080:80)"
