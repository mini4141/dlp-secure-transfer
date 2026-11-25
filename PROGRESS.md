# PROGRESS

Resume from the first unticked item. Updated at the end of each step.

## Phases (CLAUDE.md §5)
- [x] Phase 0: scaffold
- [x] Phase 1: local (tests green, CI green, proof index complete)
- [x] Phase 2: AWS showcase
- [x] Phase 3: destroy + verify-destroyed
- [x] Phase 4: write-up (docs/PORTFOLIO.md)

## Requirement coverage matrix (SPECS §2)
- [x] New features with Python + web technologies: FastAPI + Jinja/htmx app (screenshots)
- [x] Scalable, fault-tolerant services: 2 API replicas, SQS + DLQ, worker retries, idempotent scans (drill log)
- [x] Automate deployment/testing/monitoring/docs via CI/CD + IaC: GitHub Actions, Terraform, ArgoCD, OpenAPI docs (CI run, ArgoCD screenshot)
- [x] Containers + orchestration: Helm chart, kind/EKS, ArgoCD (kubectl/argocd logs)
- [x] Terraform: `infra/` (apply logs)
- [x] Mission-critical AWS: S3 SSE-KMS, SQS DLQ, RDS, Pod Identity least privilege, private DB (resources.txt)
- [x] Go: DLP worker (Go tests)
- [x] Cloud security: PII obfuscation, redaction, presigned TTLs, Argon2, audit (tests + screenshots)
- [x] Distributed systems / SaaS: API -> queue -> worker, RBAC (trace screenshot)

## Phase 1 checklist (SPECS §9)
- [x] `tests/`: pytest JUnit, go test, integration, Playwright report
- [x] screenshots: 01-send-form, 02-scanning, 03-approval-findings, 04-redacted-preview, 05-recipient-download, 06-limit-reached, 07-audit-log, 08-argocd-app, 09-trace-api-to-worker
- [x] logs: worker-scan.log (no raw PII), drill-worker-crash.log, kind-get-all.txt
- [x] scripts/test-all.sh green
- [x] CI green on main
- [x] proof/README.md index complete

## Phase 2 checklist (SPECS §10)
- [x] `aws sts get-caller-identity` OK
- [x] screenshots: 01-eks-approval, 02-eks-download, 03-eks-audit, 04-eks-argocd
- [x] logs: s3-head-object-sse.json (aws:kms), sqs-attributes.json, terraform-apply.log, resources.txt
- [x] tests/playwright-eks/

## Phase 3 checklist (SPECS §11)
- [x] destroy.sh run (ArgoCD app + LB deleted, bucket emptied, terraform destroy)
- [x] verify-destroyed.sh: no EKS, RDS, SQS, S3, ELB; KMS pending deletion
- [x] proof/phase3-destroy/verify-destroyed.txt

## Phase 4 checklist
- [x] docs/PORTFOLIO.md (problem, Mermaid diagram, stack table, screenshots, hard parts, cost, reproduce)
- [x] README.md current, docs/AI_USAGE.md written
- [x] everything committed and pushed

## Definition of done (CLAUDE.md §12)
- [x] every stack item in §2 used in running code
- [x] Phase 1 proof complete, tests green locally and in CI
- [x] Phase 2 proof complete
- [x] Phase 3 nothing billable left
- [x] PORTFOLIO.md + README.md written, pushed
