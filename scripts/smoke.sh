#!/usr/bin/env bash
# End-to-end check of the API contract. Usage: scripts/smoke.sh [BASE_URL]
# Needs ENABLE_FAILURE_SIMULATION=true on the target for the failover checks.
BASE="${1:-http://localhost:8000}"; BASE="${BASE%/}"
pass=0; fail=0
ok()   { echo "  PASS  $1"; pass=$((pass+1)); }
bad()  { echo "  FAIL  $1"; echo "        $2"; fail=$((fail+1)); }
post() { # session message [header]
  local h=(); [[ -n "${3:-}" ]] && h=(-H "X-Simulate-Failure: $3")
  curl -s -w '\n%{http_code}' -X POST "$BASE/chat" -H 'Content-Type: application/json' "${h[@]}" \
    -d "{\"session_id\":\"$1\",\"message\":\"$2\"}"
}
body() { echo "$1" | sed '$d'; }
code() { echo "$1" | tail -n1; }

RUN="$RANDOM$RANDOM"
MSG="Reply with one short sentence about the number $RUN"
echo "Smoke test against $BASE"

r=$(curl -s -w '\n%{http_code}' "$BASE/health")
[[ "$(code "$r")" == 200 && "$(body "$r")" == *'"status":"ok"'* ]] && ok "GET /health" || bad "GET /health" "$r"

a=$(post "smoke-a-$RUN" "$MSG")
[[ "$(code "$a")" == 200 && "$(body "$a")" == *'"resolution_source":"LIVE_INFERENCE"'* ]] && ok "live inference" || bad "live inference" "$a"

b=$(post "smoke-b-$RUN" "$MSG")
[[ "$(code "$b")" == 200 && "$(body "$b")" == *'"resolution_source":"LLM_CACHE"'* && "$(body "$b")" == *'"key_id":null'* ]] \
  && ok "cache hit in a new session (key_id null)" || bad "cache hit" "$b"

c=$(post "smoke-c-$RUN" "Name a prime number above $RUN" "key_1=429")
[[ "$(code "$c")" == 200 && "$(body "$c")" == *'"key_id":"key_2"'* && "$(body "$c")" == *'"fallback_attempts":1'* ]] \
  && ok "failover key_1=429 -> key_2" || bad "failover" "$c"

d=$(post "smoke-d-$RUN" "Anything $RUN" "*=429")
[[ "$(code "$d")" == 503 && "$(body "$d")" == *'all providers unavailable'* ]] && ok "all keys fail -> 503" || bad "503" "$d"

h=$(curl -s -w '\n%{http_code}' "$BASE/sessions/smoke-d-$RUN/messages")
[[ "$(code "$h")" == 404 ]] && ok "failed request not stored (404)" || bad "history after 503" "$h"

h=$(curl -s -w '\n%{http_code}' "$BASE/sessions/smoke-a-$RUN/messages")
[[ "$(code "$h")" == 200 && "$(body "$h")" == *'"role":"assistant"'* ]] && ok "GET history" || bad "history" "$h"

e=$(post "smoke-e-$RUN" "   ")
[[ "$(code "$e")" == 422 ]] && ok "empty message -> 422" || bad "422" "$e"

echo; echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
