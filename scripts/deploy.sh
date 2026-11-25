#!/usr/bin/env bash
# One-command deploy: backend -> Fly.io (with a /data volume), frontend -> Vercel.
# Requirements: flyctl (https://fly.io/docs/flyctl/install/), Node.js (uses npx vercel), curl.
# Optional env: FLY_APP, FLY_REGION (default bom), VERCEL_PROJECT, LLM_API_KEYS
set -euo pipefail
cd "$(dirname "$0")/.."

STATE=.deploy-state
[[ -f $STATE ]] && source $STATE
FLY=$(command -v fly || command -v flyctl || true)
[[ -z "$FLY" ]] && { echo "Install flyctl first: https://fly.io/docs/flyctl/install/"; exit 1; }
command -v npx >/dev/null || { echo "Node.js (npx) is required for the Vercel deploy."; exit 1; }

FLY_APP="${FLY_APP:-lyftr-chat-$(whoami | tr -cd 'a-z0-9' | cut -c1-10)-$RANDOM}"
FLY_REGION="${FLY_REGION:-bom}"
VERCEL_PROJECT="${VERCEL_PROJECT:-$FLY_APP-ui}"
echo "FLY_APP=$FLY_APP" > $STATE; echo "VERCEL_PROJECT=$VERCEL_PROJECT" >> $STATE

# ---- keys ----
if [[ -z "${LLM_API_KEYS:-}" && -f .env ]]; then LLM_API_KEYS=$(grep '^LLM_API_KEYS=' .env | cut -d= -f2- || true); fi
if [[ -z "${LLM_API_KEYS:-}" || "$LLM_API_KEYS" == *your-gemini-key* ]]; then
  read -rsp "LLM_API_KEYS (comma-separated, 2+): " LLM_API_KEYS; echo
fi
LLM_API_KEYS=$(echo "$LLM_API_KEYS" | tr -d ' ')

# ---- backend (Fly.io) ----
"$FLY" auth whoami >/dev/null 2>&1 || "$FLY" auth login
if ! "$FLY" status --app "$FLY_APP" >/dev/null 2>&1; then
  "$FLY" apps create "$FLY_APP"
  "$FLY" volumes create data --size 1 --region "$FLY_REGION" --app "$FLY_APP" --yes
fi
sed -e "s/__APP_NAME__/$FLY_APP/" -e "s/__REGION__/$FLY_REGION/" backend/fly.toml.template > backend/fly.toml
BACKEND_URL="https://$FLY_APP.fly.dev"
"$FLY" secrets set --app "$FLY_APP" --stage \
  "LLM_API_KEYS=$LLM_API_KEYS" "ALLOWED_ORIGINS=http://localhost:3000"
(cd backend && "$FLY" deploy --app "$FLY_APP" --ha=false --yes)
echo "Backend live: $BACKEND_URL"

# ---- frontend (Vercel) ----
cd frontend
npx --yes vercel whoami >/dev/null 2>&1 || npx --yes vercel login
npx --yes vercel link --yes --project "$VERCEL_PROJECT"
DEPLOY_URL=$(npx --yes vercel deploy --prod --yes --build-env "VITE_API_URL=$BACKEND_URL" | tail -n1)
cd ..
FRONTEND_URL="https://$VERCEL_PROJECT.vercel.app"
curl -fsI "$FRONTEND_URL" >/dev/null 2>&1 || FRONTEND_URL="$DEPLOY_URL"
echo "Frontend live: $FRONTEND_URL"

# ---- allow the frontend origin on the backend ----
"$FLY" secrets set --app "$FLY_APP" "ALLOWED_ORIGINS=$FRONTEND_URL,http://localhost:3000"

echo; echo "Waiting for backend..."
for _ in $(seq 1 30); do curl -fs "$BACKEND_URL/health" >/dev/null 2>&1 && break; sleep 3; done
bash scripts/smoke.sh "$BACKEND_URL" || true

cat <<DONE

Done.
  Frontend: $FRONTEND_URL
  Backend:  $BACKEND_URL/health
Put both URLs in README section 1 and the submission form.
If the frontend asks for a login, open it in an incognito window; the production alias should be public.
DONE
