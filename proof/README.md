# Proof index

Every artifact is produced by a script against the running system (`scripts/capture-proof.sh`, `scripts/test-all.sh`),
not by hand. Logs are redacted (12-digit account IDs, keys, tokens, passwords). Fake PII only.

## Phase 1: local (docker compose + kind/ArgoCD)

### Screenshots (`phase1-local/screenshots/`)
| File | Proves |
|---|---|
| `01-send-form.png` | Sender form: recipients, expiry, link password, download limit, file picker (F2) |
| `02-scanning.png` | Transfer right after upload, status `scanning` (SQS message queued) |
| `03-approval-findings.png` | Approver sees DLP findings with **obfuscated** samples (`4111 **** **** 1111`, `ta***@example.com`) and a redacted preview (F3/F4) |
| `04-redacted-preview.png` | Redacted copy preview: `[REDACTED:card]`, `[REDACTED:email]`, `[REDACTED:phone]` |
| `05-recipient-download.png` | Recipient file list after the link password (Argon2id) check (F5) |
| `06-limit-reached.png` | The download beyond the limit is refused: "Download limit reached" |
| `07-audit-log.png` | Admin audit log: created, uploaded, scan.completed, approved, downloaded, denied (F6) |
| `08-argocd-app.png` | ArgoCD (watching this public repo) shows the app Synced + Healthy on kind |
| `09-trace-api-to-worker.png` | One Jaeger trace: API finalize -> `sqs.send` -> Go worker `dlp.scan` -> API scan-results (context propagated in SQS message attributes) |

### Tests (`phase1-local/tests/`)
| File | Proves |
|---|---|
| `pytest-junit.xml`, `pytest.log` | One pytest per feature: create transfer, scan callback (idempotent), approve, download with password + limit + expiry, audit trail + append-only grants |
| `go-test.log` | Go detectors (card+Luhn, My Number check digit, IBAN mod 97, phone, email), obfuscation/redaction, docx/pdf extraction, HMAC signing |
| `integration-junit.xml`, `integration.log` | Upload -> S3 -> SQS -> Go worker -> findings against moto + Postgres |
| `playwright/`, `playwright.log` | Sender -> approver (redacted) -> recipient download -> limit -> audit journey (compose) |
| `playwright-kind/` | The same journey against the kind deployment managed by ArgoCD |
| `playwright-argocd/` | ArgoCD UI check (Synced/Healthy) |
| `ruff.log`, `golangci-lint.log`, `helm-lint.log`, `terraform-validate.log` | Lint and static validation |

### Logs (`phase1-local/logs/`)
| File | Proves |
|---|---|
| `worker-scan.log` | Structured JSON worker log (scan received/completed with counts only) |
| `pii-in-logs-check.txt` | Zero raw cards/emails in the worker and API logs |
| `drill-worker-crash.log` | F7 drill: worker killed mid-scan, SQS redelivers (`receive_count: 2`), one findings row, one `scan.completed` |
| `kind-get-all.txt` | kind cluster: 2 API replicas, worker, migrations Job completed, ArgoCD application Synced/Healthy |
| `prometheus-metrics.txt` | `/metrics` of API (FastAPI instrumentator + `dlp_*` counters) and worker (`promhttp`) |
| `api-structured.log`, `compose-ps.txt` | Structured API logs, compose service state |

## Phase 2: AWS (`phase2-cloud/`)
Filled in by `scripts/deploy.sh` (see `docs/PORTFOLIO.md`).

## Phase 3: destroy (`phase3-destroy/`)
`verify-destroyed.txt` from `scripts/verify-destroyed.sh`.
