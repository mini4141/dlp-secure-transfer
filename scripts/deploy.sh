#!/usr/bin/env bash
# Phase 2: build the AWS showcase from this PC. Terraform -> ECR push -> ArgoCD (Helm) -> app -> smoke/e2e + proof.
# GitHub Actions never holds AWS credentials; everything account-specific is injected here as ArgoCD parameters.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/aws-env.sh
PROOF=proof/phase2-cloud
mkdir -p "$PROOF"/{logs,tests,screenshots} .local
START=$(date +%s)

echo "== 0. identity"
aws sts get-caller-identity --output json | redact

if [ "$(git rev-parse HEAD)" != "$(git ls-remote origin refs/heads/main | cut -f1)" ]; then
  echo "ERROR: push HEAD to origin/main first: ArgoCD syncs the chart from GitHub." >&2; exit 1
fi
TAG="$(git rev-parse --short HEAD)"
ARGOCD_CHART_VERSION="${ARGOCD_CHART_VERSION:-10.19.1}"

echo "== 1. terraform apply"
(cd infra && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false -no-color) 2>&1 | redact | tee "$PROOF/logs/terraform-apply.log"
tf() { (cd infra && terraform output -raw "$1"); }
ECR_API=$(tf ecr_api); ECR_WORKER=$(tf ecr_worker); BUCKET=$(tf bucket); QUEUE=$(tf queue_name)
RDS=$(tf rds_address); DBPW=$(tf db_password); KMS_ID=$(tf kms_key_id)
echo "$KMS_ID" > .local/kms-key-id
REGISTRY="${ECR_API%%/*}"

echo "== 2. kubeconfig + nodes"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG_EKS" --alias dlp-eks >/dev/null
export KUBECONFIG="$KUBECONFIG_EKS"
for _ in $(seq 1 60); do
  [ "$(kubectl get nodes --no-headers 2>/dev/null | grep -c ' Ready')" -ge 2 ] && break; sleep 10
done
kubectl get nodes -o wide | redact

echo "== 3. build + push images ($TAG)"
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker build -q -t "$ECR_API:$TAG" api >/dev/null
docker build -q -t "$ECR_WORKER:$TAG" worker >/dev/null
docker push -q "$ECR_API:$TAG" >/dev/null
docker push -q "$ECR_WORKER:$TAG" >/dev/null

echo "== 4. ArgoCD (official chart)"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo update argo >/dev/null
helm upgrade --install argocd argo/argo-cd --version "$ARGOCD_CHART_VERSION" -n argocd --create-namespace \
  --set dex.enabled=false --set notifications.enabled=false --set applicationSet.enabled=false \
  --set-string 'configs.params.server\.insecure=true' --wait --timeout 10m >/dev/null

echo "== 5. Application with injected parameters"
rand() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
[ -f .local/cloud-secrets.env ] || cat > .local/cloud-secrets.env <<EOF
JWT_SECRET=$(rand 48)
HMAC_SECRET=$(rand 48)
DB_APP_PASSWORD=$(rand 24)
SEED_PASSWORD=$(rand 16)
EOF
source .local/cloud-secrets.env
bash scripts/render-app.sh values-eks.yaml \
  "image.api.repository=$ECR_API" "image.api.tag=$TAG" \
  "image.worker.repository=$ECR_WORKER" "image.worker.tag=$TAG" \
  "db.host=$RDS" "config.bucket=$BUCKET" "config.queueName=$QUEUE" "config.region=$AWS_REGION" \
  "secrets.dbOwnerPassword=$DBPW" "secrets.dbAppPassword=$DB_APP_PASSWORD" \
  "secrets.jwtSecret=$JWT_SECRET" "secrets.scanHmacSecret=$HMAC_SECRET" "secrets.seedPassword=$SEED_PASSWORD" \
  | kubectl apply -f -

echo "== 6. wait for sync + health (migrations Job runs as an ArgoCD Sync hook)"
for _ in $(seq 1 60); do kubectl -n argocd get application dlp-secure-transfer >/dev/null 2>&1 && break; sleep 2; done
kubectl -n argocd wait application/dlp-secure-transfer --for=jsonpath='{.status.sync.status}'=Synced --timeout=900s
kubectl -n argocd wait application/dlp-secure-transfer --for=jsonpath='{.status.health.status}'=Healthy --timeout=900s
kubectl -n dlp rollout status deploy/dlp-secure-transfer-api --timeout=300s

echo "== 7. wait for the NLB"
HOST=""
for _ in $(seq 1 60); do
  HOST=$(kubectl -n dlp get svc dlp-secure-transfer-api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
  [ -n "$HOST" ] && break; sleep 10
done
[ -n "$HOST" ] || { echo "NLB never got a hostname" >&2; exit 1; }
BASE_URL="http://$HOST"
for _ in $(seq 1 60); do curl -fsS -m 5 "$BASE_URL/healthz" >/dev/null 2>&1 && break; sleep 10; done
curl -fsS "$BASE_URL/healthz"; echo
echo "$BASE_URL" > .local/base-url

echo "== 8. seed (also runs on API start)"
bash scripts/seed.sh k8s dlp | redact || true

echo "== 9. e2e + proof against $BASE_URL"
BASE_URL="$BASE_URL" SEED_PASSWORD="$SEED_PASSWORD" bash scripts/capture-proof.sh phase2
echo "deploy finished in $(( ($(date +%s) - START) / 60 )) min. Run scripts/destroy.sh when done capturing."
