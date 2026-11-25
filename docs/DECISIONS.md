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
