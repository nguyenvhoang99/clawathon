#!/usr/bin/env bash
# Demo smoke test for bill-splitter (manual expenses, no OCR)
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8080}"
HDR=(
  -H "Content-Type: application/json"
  -H "X-GreenNode-AgentBase-Custom-Team-Id: team-bill-demo"
  -H "X-GreenNode-AgentBase-Session-Id: session-1"
)

echo "=== Register Alice (creditor) ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"register_member","display_name":"Alice","bank_bin":"970422","account_no":"0123456789","account_name":"NGUYEN THI A"}'

echo ""
echo "=== Register Bob ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: bob" \
  -d '{"action":"register_member","display_name":"Bob"}'

echo ""
echo "=== Register Charlie ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: charlie" \
  -d '{"action":"register_member","display_name":"Charlie"}'

echo ""
echo "=== Alice pays dinner 900k split 3 ways ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"add_expense","total_vnd":900000,"category":"food","merchant":"Seafood BBQ","payer_id":"alice","member_ids":["alice","bob","charlie"]}'

echo ""
echo "=== Bob pays taxi 300k split 3 ways ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: bob" \
  -d '{"action":"add_expense","total_vnd":300000,"category":"transport","merchant":"Grab","payer_id":"bob","member_ids":["alice","bob","charlie"]}'

echo ""
echo "=== List balances ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"list_balances"}'

echo ""
echo "=== Confirm bills ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"confirm_bills"}'

echo ""
echo "=== Finalize settlement ==="
curl -s -X POST "$BASE_URL/invocations" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"finalize"}'

echo ""
