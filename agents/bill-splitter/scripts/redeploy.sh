#!/usr/bin/env bash
# Build and redeploy bill-splitter to AgentBase managed CR.
# Requires IAM credentials (.greennode.json) and agents/bill-splitter/.env
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
AGENT_DIR="$ROOT/agents/bill-splitter"
SCRIPTS="$ROOT/.cursor/skills/agentbase/scripts"
IMAGE_NAME="${IMAGE_NAME:-bill-splitter}"
IMAGE_TAG="${IMAGE_TAG:-v$(date +%Y%m%d%H%M%S)}"
RUNTIME_ID="${RUNTIME_ID:-runtime-cfe9ca41-d42d-4360-874a-d98d65578f74}"
FLAVOR="${FLAVOR:-runtime-s2-general-2x4}"

if [[ ! -f "$SCRIPTS/check_credentials.sh" ]]; then
  echo "ERROR: AgentBase scripts not found at $SCRIPTS" >&2
  exit 1
fi

echo "=== Checking IAM credentials ==="
if ! bash "$SCRIPTS/check_credentials.sh" iam >/dev/null 2>&1; then
  echo "ERROR: IAM credentials missing. Configure via agentbase auth-setup." >&2
  exit 1
fi

echo "=== Docker login (AgentBase CR) ==="
bash "$SCRIPTS/cr.sh" credentials docker-login

REPO_JSON=$(bash "$SCRIPTS/cr.sh" repo get)
REGISTRY=$(echo "$REPO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['registryUrl'])")
REPO_NAME=$(echo "$REPO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")

FULL_IMAGE="$REGISTRY/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG"
echo "=== Building $FULL_IMAGE ==="
docker build -t "$FULL_IMAGE" "$AGENT_DIR"

echo "=== Pushing image ==="
docker push "$FULL_IMAGE"

ENV_FILE="$AGENT_DIR/.env"
UPDATE_ARGS=(update "$RUNTIME_ID" --image "$FULL_IMAGE" --flavor "$FLAVOR" --from-cr)
if [[ -f "$ENV_FILE" ]]; then
  UPDATE_ARGS+=(--env-file "$ENV_FILE")
fi

echo "=== Updating runtime $RUNTIME_ID ==="
bash "$SCRIPTS/runtime.sh" "${UPDATE_ARGS[@]}"

echo ""
echo "OK: Deployed $FULL_IMAGE to runtime $RUNTIME_ID"
echo "Run: cd web && bash scripts/verify_live.sh"
