#!/usr/bin/env bash
# Phase 3: tear everything down. Idempotent; safe to re-run. Removes anything that would block `terraform destroy`
# first (ArgoCD app + the LoadBalancer Service/NLB, S3 versions, ECR images), then destroys the Terraform stack.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/aws-env.sh
mkdir -p proof/phase3-destroy .local

tfo() { (cd infra && terraform output -raw "$1" 2>/dev/null) || true; }
BUCKET=$(tfo bucket)
[ -n "$BUCKET" ] || BUCKET="${CLUSTER_NAME}-$(aws sts get-caller-identity --query Account --output text)-${AWS_REGION}"

echo "== 1. ArgoCD application (cascade) and the LoadBalancer Service"
if [ -f "$KUBECONFIG_EKS" ] && KUBECONFIG="$KUBECONFIG_EKS" kubectl get ns >/dev/null 2>&1; then
  export KUBECONFIG="$KUBECONFIG_EKS"
  kubectl -n argocd delete application dlp-secure-transfer --ignore-not-found --wait --timeout=300s
  kubectl -n dlp delete svc dlp-secure-transfer-api --ignore-not-found --wait --timeout=300s
  kubectl delete ns dlp --ignore-not-found --wait --timeout=300s
else
  echo "cluster not reachable (already gone?), skipping in-cluster cleanup"
fi

echo "== 2. wait until no load balancer of this cluster remains"
lb_left() {
  local n=0 arn name
  for arn in $(aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerArn' --output text 2>/dev/null); do
    aws elbv2 describe-tags --resource-arns "$arn" --query "TagDescriptions[].Tags[?Key=='kubernetes.io/cluster/${CLUSTER_NAME}' || (Key=='Project' && Value=='dlp-secure-transfer')]" --output text 2>/dev/null | grep -q . && n=$((n+1))
  done
  # this account only allows classic ELBs (see docs/DECISIONS.md)
  for name in $(aws elb describe-load-balancers --query 'LoadBalancerDescriptions[].LoadBalancerName' --output text 2>/dev/null); do
    aws elb describe-tags --load-balancer-names "$name" --query "TagDescriptions[].Tags[?Key=='kubernetes.io/cluster/${CLUSTER_NAME}' || (Key=='Project' && Value=='dlp-secure-transfer')]" --output text 2>/dev/null | grep -q . && n=$((n+1))
  done
  echo "$n"
}
for _ in $(seq 1 40); do [ "$(lb_left)" = "0" ] && break; echo "  NLB still deleting..."; sleep 10; done

echo "== 3. empty the bucket (all versions and delete markers)"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  for kind in Versions DeleteMarkers; do
    while :; do
      payload=$(aws s3api list-object-versions --bucket "$BUCKET" --max-items 500 --output json \
        --query "{Objects: ${kind}[].{Key:Key,VersionId:VersionId}}" 2>/dev/null || echo null)
      echo "$payload" | grep -q '"Key"' || break
      aws s3api delete-objects --bucket "$BUCKET" --delete "$payload" >/dev/null
    done
  done
fi

echo "== 4. delete ECR images"
for repo in api worker; do
  ids=$(aws ecr list-images --repository-name "${CLUSTER_NAME}/${repo}" --query 'imageIds[*]' --output json 2>/dev/null || echo "[]")
  [ "$ids" != "[]" ] && [ -n "$ids" ] && aws ecr batch-delete-image --repository-name "${CLUSTER_NAME}/${repo}" --image-ids "$ids" >/dev/null
done

echo "== 5. terraform destroy"
(cd infra && terraform init -input=false >/dev/null && terraform destroy -auto-approve -input=false -no-color) 2>&1 | redact | tee proof/phase3-destroy/terraform-destroy.log
rc=${PIPESTATUS[0]}
rm -f "$KUBECONFIG_EKS" .local/base-url
echo "destroy finished with exit code $rc (KMS key stays in PendingDeletion for 7 days)"
exit "$rc"
