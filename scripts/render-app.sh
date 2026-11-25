#!/usr/bin/env bash
# Render deploy/argocd/application.yaml to stdout.
# Usage: render-app.sh <values-file> [name=value ...]   (extra args become Helm parameters)
# Pure bash on purpose: sed's `r` ordering is unreliable in Git Bash.
set -euo pipefail
cd "$(dirname "$0")/.."
values="$1"; shift
revision="${TARGET_REVISION:-main}"

params=""
if [ "$#" -eq 0 ]; then
  params=$'        []\n'
else
  for kv in "$@"; do
    params+="        - name: ${kv%%=*}"$'\n'"          value: \"${kv#*=}\""$'\n'"          forceString: true"$'\n'
  done
fi

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    *__PARAMETERS__*) printf '%s' "$params" ;;
    *) line=${line//__REVISION__/$revision}; line=${line//__VALUES_FILE__/$values}; printf '%s\n' "$line" ;;
  esac
done < deploy/argocd/application.yaml
