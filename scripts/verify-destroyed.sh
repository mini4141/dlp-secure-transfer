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
  for name in $(aws elb describe-load-balancers --query 'LoadBalancerDescriptions[].LoadBalancerName' --output text 2>/dev/null); do
    aws elb describe-tags --load-balancer-names "$name" --query "TagDescriptions[].Tags[?Key=='kubernetes.io/cluster/${CLUSTER_NAME}' || (Key=='Project' && Value=='dlp-secure-transfer')]" --output text | grep -q . && n=$((n+1))
  done
  check "no load balancers of this project (ELBv2 + classic)" "$n"

  echo "-- KMS key must be pending deletion"
  found=0
  for kid in $(aws kms list-keys --query 'Keys[].KeyId' --output text); do
    desc=$(aws kms describe-key --key-id "$kid" --query 'KeyMetadata.[Description,KeyState]' --output text 2>/dev/null || true)
    case "$desc" in "${CLUSTER_NAME} data key"*)
      found=1; state=$(echo "$desc" | awk '{print $NF}')
      if [ "$state" = "PendingDeletion" ]; then echo "OK    KMS key $kid is PendingDeletion"; else echo "FAIL  KMS key $kid state=$state"; FAIL=1; fi;; esac
  done
  [ "$found" = 1 ] || echo "OK    no KMS key with this project's description (already purged)"

  echo "-- resourcegroupstaggingapi (Project=dlp-secure-transfer); can lag after deletion, so each hit is confirmed by a direct describe call"
  still_exists() { # ARN -> 0 if the resource really exists (or cannot be confirmed), 1 if a describe call says it is gone
    local arn="$1" id="${1##*/}"
    case "$arn" in
      *:security-group-rule/*) aws ec2 describe-security-group-rules --security-group-rule-ids "$id" >/dev/null 2>&1 ;;
      *:security-group/*)      aws ec2 describe-security-groups --group-ids "$id" >/dev/null 2>&1 ;;
      *:subnet/*)              aws ec2 describe-subnets --subnet-ids "$id" >/dev/null 2>&1 ;;
      *:vpc/*)                 aws ec2 describe-vpcs --vpc-ids "$id" >/dev/null 2>&1 ;;
      *:internet-gateway/*)    aws ec2 describe-internet-gateways --internet-gateway-ids "$id" >/dev/null 2>&1 ;;
      *:route-table/*)         aws ec2 describe-route-tables --route-table-ids "$id" >/dev/null 2>&1 ;;
      *:instance/*)            [ "$(aws ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null)" != "terminated" ] ;;
      *:volume/*)              aws ec2 describe-volumes --volume-ids "$id" >/dev/null 2>&1 ;;
      *:network-interface/*)   aws ec2 describe-network-interfaces --network-interface-ids "$id" >/dev/null 2>&1 ;;
      *) return 0 ;;
    esac
  }
  left=""
  for attempt in $(seq 1 6); do
    left=""
    for arn in $(aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=dlp-secure-transfer --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '	' '
' | grep -v ':kms:'); do
      if still_exists "$arn"; then left="$left$arn"$'
'; else echo "  (stale tagging entry, describe says gone: ${arn##*:})"; fi
    done
    [ -z "$left" ] && break
    echo "  attempt $attempt: $(printf '%s' "$left" | grep -c .) resource(s) confirmed present, waiting 30s"; sleep 30
  done
  if [ -z "$left" ]; then echo "OK    nothing billable tagged Project=dlp-secure-transfer"; else echo "FAIL  still present:"; printf '%s' "$left" | sed 's/^/        /'; FAIL=1; fi

  [ "$FAIL" = 0 ] && echo "RESULT: ALL CLEAN" || echo "RESULT: RESOURCES REMAIN"
  return "$FAIL"
}

run 2>&1 | redact | tee "$OUT"
exit "${PIPESTATUS[0]}"
