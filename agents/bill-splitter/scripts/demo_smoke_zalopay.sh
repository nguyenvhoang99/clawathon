#!/usr/bin/env bash
# Bill-splitter smoke test with ZaloPay wallet fields (phone as account_no)
set -euo pipefail

BASE_URL="${1:-https://endpoint-5ca9ea82-4d2a-4526-be86-b731ea37355d.agentbase-runtime.aiplatform.vngcloud.vn}"
ZALOPAY_BIN="${ZALOPAY_BIN:?Set ZALOPAY_BIN (NAPAS BIN for ZaloPay wallet)}"
TEAM_ID="${TEAM_ID:-team-zalopay-demo}"
SESSION_ID="${SESSION_ID:-session-zp-1}"

HDR=(
  -H "Content-Type: application/json"
  -H "X-GreenNode-AgentBase-Custom-Team-Id: $TEAM_ID"
  -H "X-GreenNode-AgentBase-Session-Id: $SESSION_ID"
)

register() {
  local id="$1" name="$2" phone="$3"
  curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
    -H "X-GreenNode-AgentBase-User-Id: $id" \
    -d "{\"action\":\"register_member\",\"member_id\":\"$id\",\"display_name\":\"$name\",\"bank_bin\":\"$ZALOPAY_BIN\",\"bank_code\":\"ZLP\",\"account_no\":\"$phone\",\"account_name\":\"$(echo "$name" | tr '[:lower:]' '[:upper:]')\"}"
  echo ""
}

echo "=== Register Alice (ZaloPay creditor) ==="
register alice Alice 0901234567

echo "=== Register Bob ==="
register bob Bob 0902345678

echo "=== Register Charlie ==="
register charlie Charlie 0903456789

echo "=== Alice pays dinner 900k ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"add_expense","total_vnd":900000,"category":"food","merchant":"Seafood BBQ","payer_id":"alice","member_ids":["alice","bob","charlie"]}'
echo ""

echo "=== Bob pays taxi 300k ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: bob" \
  -d '{"action":"add_expense","total_vnd":300000,"category":"transport","merchant":"Grab","payer_id":"bob","member_ids":["alice","bob","charlie"]}'
echo ""

echo "=== Finalize ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"finalize"}' | python3 -m json.tool
echo ""
