#!/usr/bin/env bash
# Creates .env interactively (or from the LLM_API_KEYS environment variable).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]] && grep -q '^LLM_API_KEYS=' .env && ! grep -q 'your-gemini-key' .env; then
  echo ".env already exists with keys. Delete it to re-run setup."
  exit 0
fi

keys="${LLM_API_KEYS:-}"
if [[ -z "$keys" ]]; then
  echo "Enter your API keys, comma-separated (at least 2; get free Gemini keys at https://aistudio.google.com/apikey)."
  read -rsp "LLM_API_KEYS: " keys
  echo
fi

keys="$(echo "$keys" | tr -d ' ')"
count=$(echo "$keys" | tr ',' '\n' | grep -c . || true)
if (( count < 2 )); then
  echo "Need at least 2 keys for failover (got $count)." >&2
  exit 1
fi

{ grep -v '^LLM_API_KEYS=' .env.example; echo "LLM_API_KEYS=$keys"; } > .env
echo "Wrote .env with $count keys."
