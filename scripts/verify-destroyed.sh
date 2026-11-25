#!/usr/bin/env bash
# Lists anything still tagged Project=dlp-secure-transfer and runs the specific checks from SPECS.md section 11.
# Exits non-zero if anything billable remains. Output is saved (redacted) to proof/phase3-destroy/verify-destroyed.txt.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/aws-env.sh
mkdir -p proof/phase3-destroy
OUT=proof/phase3-destroy/verify-destroyed.txt
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${CLUSTER_NAME}-${ACCOUNT}-${AWS_REGION}"
FAIL=0

run() {
  echo "verify-destroyed: $(date -u +%Y-%m-%dT%H:%M:%SZ) profile=$AWS_PROFILE region=$AWS_REGION"
  check() { # description, count-of-leftovers
    if [ "$2" = "0" ]; then echo "OK    $1"; else echo "FAIL  $1 ($2 left)"; FAIL=1; fi
  }

  echo "-- specific checks (direct describe calls)"
  n=$(aws eks list-clusters --query "length(clusters[?@=='${CLUSTER_NAME}'])" --output text); check "no EKS cluster" "$n"
  n=$(aws rds describe-db-instances --query "length(DBInstances[?DBInstanceIdentifier=='${CLUSTER_NAME}'])" --output text 2>/dev/null || echo 0); check "no RDS instance" "$n"
  n=$(aws sqs list-queues --queue-name-prefix "${CLUSTER_NAME}" --query 'length(QueueUrls || `[]`)' --output text); check "no SQS queues" "$n"
  n=$(aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1 && echo 1 || echo 0); check "no S3 bucket" "$n"
  n=$(aws ecr describe-repositories --query "length(repositories[?starts_with(repositoryName,'${CLUSTER_NAME}/')])" --output text 2>/dev/null || echo 0); check "no ECR repositories" "$n"
  n=$(aws ec2 describe-vpcs --filters "Name=tag:Project,Values=dlp-secure-transfer" --query 'length(Vpcs)' --output text); check "no VPC" "$n"
  n=$(aws ec2 describe-nat-gateways --filter "Name=tag:Project,Values=dlp-secure-transfer" "Name=state,Values=available,pending" --query 'length(NatGateways)' --output text); check "no NAT gateways" "$n"
  n=$(aws iam list-roles --query "length(Roles[?starts_with(RoleName,'${CLUSTER_NAME}-')])" --output text); check "no IAM roles" "$n"
  n=$(aws logs describe-log-groups --log-group-name-prefix "/aws/eks/${CLUSTER_NAME}" --query 'length(logGroups)' --output text); check "no CloudWatch log groups" "$n"

  n=0
  for arn in $(aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerArn' --output text 2>/dev/null); do
    aws elbv2 describe-tags --resource-arns "$arn" --query "TagDescriptions[].Tags[?Key=='kubernetes.io/cluster/${CLUSTER_NAME}' || (Key=='Project' && Value=='dlp-secure-transfer')]" --output text | grep -q . && n=$((n+1))
  done
  m=$(aws elb describe-load-balancers --query 'length(LoadBalancerDescriptions)' --output text 2>/dev/null || echo 0)
  check "no load balancers of this project (elbv2)" "$n"; echo "      (classic ELBs in account: $m, none tagged for this project is verified via tagging API below)"

  echo "-- KMS key must be pending deletion"
  found=0
  for kid in $(aws kms list-keys --query 'Keys[].KeyId' --output text); do
    desc=$(aws kms describe-key --key-id "$kid" --query 'KeyMetadata.[Description,KeyState]' --output text 2>/dev/null || true)
    case "$desc" in "${CLUSTER_NAME} data key"*)
      found=1; state=$(echo "$desc" | awk '{print $NF}')
      if [ "$state" = "PendingDeletion" ]; then echo "OK    KMS key $kid is PendingDeletion"; else echo "FAIL  KMS key $kid state=$state"; FAIL=1; fi;; esac
  done
  [ "$found" = 1 ] || echo "OK    no KMS key with this project's description (already purged)"

  echo "-- resourcegroupstaggingapi (Project=dlp-secure-transfer); may lag a few minutes after deletion"
  left=""
  for attempt in $(seq 1 12); do
    left=$(aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=dlp-secure-transfer --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n' | grep -v ':kms:' || true)
    [ -z "$left" ] && break
    echo "  attempt $attempt: still listed: $(echo "$left" | wc -l) resource(s), waiting 30s"; sleep 30
  done
  if [ -z "$left" ]; then echo "OK    nothing billable tagged Project=dlp-secure-transfer"; else echo "FAIL  still tagged:"; echo "$left" | sed 's/^/        /'; FAIL=1; fi

  [ "$FAIL" = 0 ] && echo "RESULT: ALL CLEAN" || echo "RESULT: RESOURCES REMAIN"
  return "$FAIL"
}

run 2>&1 | redact | tee "$OUT"
exit "${PIPESTATUS[0]}"
