#!/usr/bin/env bash
# Phase 2 CLI evidence: SSE-KMS on a real uploaded object, SQS attributes (DLQ redrive), resource list, k8s state.
# There is no console login, so AWS-side visuals are rendered from the CLI. Everything is redacted before saving.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/aws-env.sh
P=proof/phase2-cloud; mkdir -p $P/logs
export KUBECONFIG="$KUBECONFIG_EKS"
tf() { (cd infra && terraform output -raw "$1"); }
BUCKET=$(tf bucket); QUEUE_URL=$(tf queue_url); DLQ_URL=$(tf dlq_url)

KEY=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix uploads/ --query 'Contents[0].Key' --output text)
aws s3api head-object --bucket "$BUCKET" --key "$KEY" --output json | redact > $P/logs/s3-head-object-sse.json
grep -q 'aws:kms' $P/logs/s3-head-object-sse.json && echo "SSE: aws:kms confirmed on $KEY"
RKEY=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix redacted/ --query 'Contents[0].Key' --output text)
aws s3api head-object --bucket "$BUCKET" --key "$RKEY" --output json | redact > $P/logs/s3-head-object-redacted-sse.json

{ aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names All --output json
  aws sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names QueueArn KmsMasterKeyId --output json
} | redact > $P/logs/sqs-attributes.json
aws s3api get-bucket-encryption --bucket "$BUCKET" --output json | redact > $P/logs/s3-bucket-encryption.json
aws s3api get-bucket-versioning --bucket "$BUCKET" --output json > $P/logs/s3-bucket-versioning.json
aws s3api get-public-access-block --bucket "$BUCKET" --output json > $P/logs/s3-public-access-block.json
aws rds describe-db-instances --db-instance-identifier "$CLUSTER_NAME" \
  --query 'DBInstances[0].{id:DBInstanceIdentifier,class:DBInstanceClass,engine:Engine,version:EngineVersion,publiclyAccessible:PubliclyAccessible,multiAZ:MultiAZ,encrypted:StorageEncrypted,status:DBInstanceStatus}' \
  --output json | redact > $P/logs/rds-describe.json
aws eks list-pod-identity-associations --cluster-name "$CLUSTER_NAME" --output json | redact > $P/logs/eks-pod-identity-associations.json

{ kubectl get nodes -o wide; echo; kubectl -n dlp get all,sa; echo; kubectl -n argocd get applications; } | redact > $P/logs/kubectl-get-all.txt
kubectl -n dlp logs deploy/dlp-secure-transfer-worker --tail=30 | redact > $P/logs/worker-eks.log
kubectl -n dlp logs deploy/dlp-secure-transfer-api --tail=30 | redact > $P/logs/api-eks.log

{
  echo "# Deployed AWS resources (Terraform outputs and tag-based inventory), account ids redacted"
  echo "region: $AWS_REGION"
  echo "cluster: $(tf cluster_name)"; echo "ecr_api: $(tf ecr_api)"; echo "ecr_worker: $(tf ecr_worker)"
  echo "bucket: $BUCKET"; echo "queue: $(tf queue_name)"; echo "dlq: $DLQ_URL"; echo "rds: $(tf rds_address)"; echo "kms: $(tf kms_key_arn)"
  echo; echo "# resourcegroupstaggingapi Project=dlp-secure-transfer"
  aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=dlp-secure-transfer --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n' | sort
} | redact > $P/resources.txt
echo "AWS evidence written to $P"
