#!/usr/bin/env bash
# Sourced by the AWS scripts. Pins the one allowed profile and region.
export AWS_PROFILE=dlp-secure-transfer-deployer
export AWS_REGION=ap-southeast-2
export AWS_DEFAULT_REGION=ap-southeast-2
export AWS_PAGER=""
export MSYS_NO_PATHCONV=1
export CLUSTER_NAME=dlp-secure-transfer
export KUBECONFIG_EKS="${KUBECONFIG_EKS:-$(cygpath -m "$PWD/.local/kubeconfig-eks" 2>/dev/null || echo "$PWD/.local/kubeconfig-eks")}"

# Redact account ids, access keys and bearer-ish tokens before anything is saved as proof.
redact() { sed -E 's/[0-9]{12}/<ACCOUNT_ID>/g; s/(AKIA|ASIA)[A-Z0-9]{16}/<ACCESS_KEY>/g; s/(password|secret|token)(["= :]+)[^ ",]+/\1\2<REDACTED>/Ig'; }
