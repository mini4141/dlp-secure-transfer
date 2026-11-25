#!/usr/bin/env bash
# Generate API docs from the FastAPI OpenAPI schema: docs/api/openapi.json + docs/api/index.html (Redoc-free, static).
set -euo pipefail
cd "$(dirname "$0")/../api"
mkdir -p ../docs/api
uv sync --frozen >/dev/null
uv run python - <<'PY'
import html
import json

from app.main import app

spec = app.openapi()
json.dump(spec, open("../docs/api/openapi.json", "w"), indent=2)
rows = []
for path, ops in sorted(spec["paths"].items()):
    for method, op in ops.items():
        rows.append(
            f"<tr><td><code>{method.upper()}</code></td><td><code>{html.escape(path)}</code></td>"
            f"<td>{html.escape(op.get('summary', ''))}</td><td>{html.escape(op.get('description', '') or '')}</td></tr>"
        )
page = (
    f"<!doctype html><meta charset=utf-8><title>{spec['info']['title']} API</title>"
    "<style>body{font:15px system-ui;margin:2rem}td,th{border-bottom:1px solid #ddd;padding:6px 10px;text-align:left}</style>"
    f"<h1>{spec['info']['title']} {spec['info']['version']}</h1><p>{html.escape(spec['info'].get('description', ''))}</p>"
    "<table><tr><th>Method</th><th>Path</th><th>Summary</th><th>Description</th></tr>" + "".join(rows) + "</table>"
)
open("../docs/api/index.html", "w").write(page)
print("wrote docs/api/openapi.json and index.html")
PY
