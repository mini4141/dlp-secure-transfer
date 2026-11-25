#!/usr/bin/env bash
# Run every local test layer; exits non-zero on the first failure.
# Reports go to proof/phase1-local/tests/ (override with OUT=...).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
ROOT="$(cygpath -m "$(pwd)" 2>/dev/null || pwd)"
OUT="${OUT:-$ROOT/proof/phase1-local/tests}"
DC="docker compose -f local/docker-compose.yml"
mkdir -p "$OUT"

echo "== lint"
(cd api && uv sync --frozen >/dev/null && uv run ruff check . | tee "$OUT/ruff.log")
if command -v golangci-lint >/dev/null; then (cd worker && golangci-lint run ./... | tee "$OUT/golangci-lint.log"); else (cd worker && go vet ./... | tee "$OUT/go-vet.log"); fi
helm lint deploy/helm/dlp-secure-transfer -f deploy/helm/dlp-secure-transfer/values-kind.yaml | tee "$OUT/helm-lint.log"
if [ -d infra ]; then (cd infra && terraform fmt -check -recursive && terraform init -backend=false -input=false >/dev/null && terraform validate | tee "$OUT/terraform-validate.log"); fi

echo "== pytest (API features, S3/SQS via moto, Postgres from compose)"
$DC up -d --wait postgres >/dev/null
(cd api && uv run pytest -q --junitxml="$OUT/pytest-junit.xml" | tee "$OUT/pytest.log")

echo "== go test (detectors, Luhn, My Number, IBAN, docx/pdf extraction)"
(cd worker && go test -v ./... 2>&1 | tee "$OUT/go-test.log")

echo "== integration (upload -> S3 -> SQS -> Go worker -> findings)"
$DC up -d --build --wait >/dev/null
(cd api && uv run pytest tests_integration -q --junitxml="$OUT/integration-junit.xml" | tee "$OUT/integration.log")

echo "== playwright (sender -> approver -> recipient)"
(cd e2e && [ -d node_modules ] || npm ci >/dev/null
 JAEGER_URL=http://localhost:26686 REPORT_DIR="$OUT/playwright" npx playwright test | tee "$OUT/playwright.log")

echo "ALL TESTS PASSED"
