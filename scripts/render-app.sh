#!/usr/bin/env bash
# Render deploy/argocd/application.yaml to stdout.
# Usage: render-app.sh <values-file> [name=value ...]   (extra args become Helm parameters)
set -euo pipefail
cd "$(dirname "$0")/.."
values="$1"; shift
revision="${TARGET_REVISION:-main}"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
if [ "$#" -eq 0 ]; then
  sed -e "s#__REVISION__#${revision}#" -e "s#__VALUES_FILE__#${values}#" -e '/parameters:/{n;d}' deploy/argocd/application.yaml | sed 's#      parameters:#      parameters: []#'
  exit 0
fi
for kv in "$@"; do
  name="${kv%%=*}"; value="${kv#*=}"
  printf '        - name: %s\n          value: "%s"\n          forceString: true\n' "$name" "$value" >> "$tmp"
done
sed -e "s#__REVISION__#${revision}#" -e "s#__VALUES_FILE__#${values}#" -e "/__PARAMETERS__/{r $tmp" -e 'd}' deploy/argocd/application.yaml
