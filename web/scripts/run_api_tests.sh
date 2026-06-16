#!/usr/bin/env bash
# Run post-deploy API verification against local proxy or live runtime.
#
# Usage:
#   bash web/scripts/run_api_tests.sh                          # smoke, local proxy :8080
#   bash web/scripts/run_api_tests.sh smoke https://endpoint-... # smoke, deployed URL
#   bash web/scripts/run_api_tests.sh full  https://endpoint-... # full E2E (~3 min)
#
# Environment (optional):
#   TEAM_ID, SESSION_ID, ZALOPAY_BIN, API_TEST_TIMEOUT
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-smoke}"
BASE_URL="${2:-${BASE_URL:-http://127.0.0.1:8080}}"
export BASE_URL
export API_TEST_MODE="$MODE"
export TEAM_ID="${TEAM_ID:-team-deploy-$(date +%Y%m%d%H%M%S)}"
export SESSION_ID="${SESSION_ID:-session-deploy-$(date +%s)}"

if [[ "$MODE" != "smoke" && "$MODE" != "full" ]]; then
  echo "Usage: $0 [smoke|full] [BASE_URL]" >&2
  exit 2
fi

echo "=== API deploy tests ==="
echo "  mode:       $MODE"
echo "  base_url:   $BASE_URL"
echo "  team_id:    $TEAM_ID"
echo "  session_id: $SESSION_ID"
echo ""

cd "$ROOT"
python3 -m unittest web.tests.test_deploy_api -v

echo ""
echo "=== All API tests passed ($MODE) ==="
