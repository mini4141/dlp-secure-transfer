# Decisions

One line each: date, decision, reason.

- 2026-11-26: Host toolchain found: Docker 29.7.2, kind 0.33.0, kubectl 1.36.1, Helm 4.3.2, Terraform 1.17.2, AWS CLI 2.42.1, uv 0.10.3 (Python 3.12.12 via uv), Go 1.27.4, Node 24.12. Reason: record versions per CLAUDE.md §3.
- 2026-11-26: Go module declares `go 1.25` and images build with `golang:1.25`; the host has Go 1.27 (backward compatible). Reason: spec pins 1.25.
- 2026-11-26: `argocd` CLI not installed; deploy/kind scripts use `kubectl` against the Application CRD (`kubectl wait --for=jsonpath`) instead of `argocd app wait`. Reason: same effect, no extra install.
- 2026-11-26: ArgoCD is installed with the official `argo-cd` Helm chart (argoproj.github.io/argo-helm), not a Bitnami chart. Reason: CLAUDE.md §3.
- 2026-11-26: Queue and bucket are bootstrapped by the API on start (`BOOTSTRAP_AWS=true`) only for moto/local; in AWS Terraform owns them. Reason: no extra init container for local stand-ins.
- 2026-11-26: The API Service itself is `type: LoadBalancer` (NLB, in-tree controller annotation) instead of a separate ingress controller. Reason: fewer moving parts, still one NLB.
- 2026-11-26: Two DB roles: owner (migrations) and `dlp_app` (runtime, no UPDATE/DELETE on `audit_events`). Reason: CLAUDE.md §11 append-only audit enforced by grants.
- 2026-11-26: Redacted copy of docx/pdf is written as a plain-text `.txt` object. Reason: re-writing binary formats is out of scope.
- 2026-11-26: Approver preview reads at most 4 KB of the redacted copy through the API. Reason: it is already redacted, so no PII passes through the pods; originals never do.
- 2026-11-26: CSRF protection relies on SameSite=Lax cookies and JSON/same-origin forms; no token. Reason: showcase scope.
- 2026-11-26: htmx is vendored from the npm package `htmx.org` into `api/app/static/`. Reason: no CDN dependency at runtime.
- 2026-11-26: Link download counter counts every file download (not whole transfers). Reason: simplest reading of "download limit".
- 2026-11-26: Worker builds with Go 1.26 (`golang:1.26-alpine`), not 1.25: current releases of otel/prometheus/aws-sdk require go >= 1.26. Reason: latest deps; pinning old ones is worse.
- 2026-11-26: Local compose publishes on non-default host ports (postgres 15432, moto 15000, api 18000, worker 19090, jaeger UI 26686). Reason: another stack on this PC already owns 5432/9090/16686/4318; mine must not collide with or touch it.
- 2026-11-26: RDS connections use `ssl=require` (encrypted, certificate not verified) via asyncpg. Reason: RDS PostgreSQL 17 forces SSL; CA bundle handling is out of scope for the showcase.
- 2026-11-26: EKS 1.36 on `AL2023_x86_64_STANDARD`, RDS PostgreSQL 17.12 (17.6 used locally is not offered by RDS). Reason: versions available in ap-southeast-2 on 2026-11-26.
- 2026-11-26: Cloud login password for the three demo users is random per deployment (`.local/cloud-secrets.env`, gitignored), not the local `demo-password`. Reason: the NLB endpoint is public.
- 2026-11-26: API image is multi-stage (uv only in the build stage); worker image runs `apk upgrade`. Reason: Trivy flagged uv 0.10.3 (CRITICAL) and alpine openssl; `golang.org/x/net` bumped to 0.63.
- 2026-11-26: Scripts convert the repo root with `cygpath -m` before passing absolute paths to native Windows tools (uv, node, kubectl). Reason: `MSYS_NO_PATHCONV=1` leaves `/c/...` paths unresolvable for them.
- 2026-11-26: The public endpoint is a Classic Load Balancer (plain `Service type: LoadBalancer`), not an NLB. Reason: ELBv2 CreateLoadBalancer fails in this AWS account with OperationNotPermitted ("account does not support creating load balancers"); classic ELB creation works. destroy/verify scripts check both ELB APIs.
