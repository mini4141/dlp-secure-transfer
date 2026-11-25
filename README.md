# DLP Secure Transfer

[![ci](https://github.com/mini4141/dlp-secure-transfer/actions/workflows/ci.yml/badge.svg)](https://github.com/mini4141/dlp-secure-transfer/actions/workflows/ci.yml)

High-security enterprise file exchange with data-loss-prevention scanning. Employees send files to external
partners through expiring, password-protected links. Every upload is scanned for PII by a Go worker, risky
transfers need an approver, and recipients only get short-lived presigned downloads. Everything is audited.
It runs on Kubernetes, deployed by ArgoCD, on Terraform-built AWS infrastructure.

> Status: scaffold. See [PROGRESS.md](PROGRESS.md).

## Architecture

See [SPECS.md](SPECS.md) section 3 (sequence diagram) and `docs/PORTFOLIO.md` once written.

## Quickstart (local)

```bash
scripts/dev-up.sh      # postgres, moto (S3+SQS), jaeger, api, worker
# open http://localhost:8000  (sam@corp.test / ava@corp.test / admin@corp.test, password in scripts/seed)
scripts/dev-down.sh
```

## Deploy / destroy (AWS)

```bash
scripts/deploy.sh      # terraform apply, ECR push, ArgoCD, app, smoke/e2e
scripts/destroy.sh && scripts/verify-destroyed.sh
```

## More

- Proof index: [proof/README.md](proof/README.md)
- Write-up: [docs/PORTFOLIO.md](docs/PORTFOLIO.md)
- Decisions: [docs/DECISIONS.md](docs/DECISIONS.md)
