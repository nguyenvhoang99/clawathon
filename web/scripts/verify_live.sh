#!/usr/bin/env bash
# E2E verification through local proxy (live agent mode)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${1:-http://127.0.0.1:3000}"
TEAM_ID="${TEAM_ID:-team-web-live}"
SESSION_ID="${SESSION_ID:-session-live-$(date +%s)}"

read_config() {
  python3 - "$WEB_DIR/config.js" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r'bankBin:\s*"([^"]*)"', text)
print(m.group(1) if m else "")
PY
}

ZALOPAY_BIN="${ZALOPAY_BIN:-$(read_config 2>/dev/null || true)}"
if [[ -z "$ZALOPAY_BIN" ]]; then
  ZALOPAY_BIN="${ZALOPAY_BIN:-970422}"
  echo "WARNING: zalopay.bankBin not set in config.js — using fallback $ZALOPAY_BIN"
fi

HDR=(
  -H "Content-Type: application/json"
  -H "X-GreenNode-AgentBase-Custom-Team-Id: $TEAM_ID"
  -H "X-GreenNode-AgentBase-Session-Id: $SESSION_ID"
)

echo "=== Team: $TEAM_ID / Session: $SESSION_ID ==="

echo ""
echo "=== 1. Weather agent ==="
curl -sf --max-time 60 -X POST "$BASE_URL/api/weather" "${HDR[@]}" \
  -d '{"message":"What is the weather in Hanoi today?"}' | python3 -m json.tool | head -20

echo ""
echo "=== 2. Trip planner (may take up to 120s) ==="
curl -sf --max-time 120 -X POST "$BASE_URL/api/trip" "${HDR[@]}" \
  -d '{"message":"10 people from Ho Chi Minh City to Da Nang, Mar 20-23, 5 million VND per person, beach and food"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('phase:', d.get('phase')); print('destination:', (d.get('trip_brief') or {}).get('destination_city'))"

echo ""
echo "=== 3. Bill splitter — register ZaloPay members ==="
register_member() {
  local id="$1" name="$2" phone="$3"
  curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" \
    -H "X-GreenNode-AgentBase-User-Id: $id" \
    -d "{\"action\":\"register_member\",\"member_id\":\"$id\",\"display_name\":\"$name\",\"bank_bin\":\"$ZALOPAY_BIN\",\"bank_code\":\"ZLP\",\"account_no\":\"$phone\",\"account_name\":\"$(echo "$name" | tr '[:lower:]' '[:upper:]')\"}"
  echo ""
}

register_member "alice" "Alice" "0901234567"
register_member "bob" "Bob" "0902345678"
register_member "charlie" "Charlie" "0903456789"

echo "=== 4. List members ==="
curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"list_members"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('members:', len(d.get('members', [])))"

echo ""
echo "=== 5. Upload receipt (structured form + OCR) ==="
UPLOAD_PAYLOAD=$(python3 <<'PY'
import base64, io, json
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    # Minimal 1x1 PNG if Pillow unavailable in verify environment
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
else:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(0, 180, 100)).save(buf, format="PNG")
    png = buf.getvalue()
print(json.dumps({
    "action": "upload_receipt",
    "image_base64": base64.b64encode(png).decode("ascii"),
    "image_media_type": "image/png",
    "payer_id": "alice",
    "merchant": "Transfer screenshot",
    "total_vnd": 150000,
    "category": "food",
    "member_ids": ["alice", "bob", "charlie"],
    "notes": "verify_live receipt upload",
}))
PY
)
UPLOAD_RESULT=$(curl -sf --max-time 120 -X POST "$BASE_URL/api/bill" "${HDR[@]}" \
  -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d "$UPLOAD_PAYLOAD")
echo "$UPLOAD_RESULT" | python3 -m json.tool | head -25

echo ""
echo "=== 6. List expenses (thumbnails + display names) ==="
EXP_RESULT=$(curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"list_expenses"}')
echo "$EXP_RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
expenses = d.get('expenses') or []
print('expense_count:', len(expenses))
if not expenses:
    raise SystemExit('FAIL: no expenses returned')
sample = expenses[0]
for key in ('payer_display_name', 'has_receipt'):
    if key not in sample:
        print(f'WARN: missing {key} — redeploy bill-splitter runtime with latest code')
print('sample merchant:', sample.get('merchant'))
print('has_receipt:', sample.get('has_receipt'))
"

echo ""
echo "=== 7. Add manual expenses ==="
curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"add_expense","total_vnd":900000,"category":"food","merchant":"Seafood BBQ","payer_id":"alice","member_ids":["alice","bob","charlie"]}'
echo ""
curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: bob" \
  -d '{"action":"add_expense","total_vnd":300000,"category":"transport","merchant":"Grab","payer_id":"bob","member_ids":["alice","bob","charlie"]}'
echo ""

echo "=== 8. List balances (with account_no) ==="
curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"list_balances"}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
bal = (d.get('balances') or {}).get('alice') or {}
print('alice account_no:', bal.get('account_no'))
if bal.get('account_no') is None:
    print('WARN: account_no missing — redeploy bill-splitter runtime with latest code')
else:
    print('OK: account_no present')
"

echo ""
echo "=== 9. Confirm bills ==="
curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"confirm_bills"}' | python3 -m json.tool

echo ""
echo "=== 10. Finalize settlement (VietQR) ==="
RESULT=$(curl -sf -X POST "$BASE_URL/api/bill" "${HDR[@]}" -H "X-GreenNode-AgentBase-User-Id: alice" \
  -d '{"action":"finalize"}')
echo "$RESULT" | python3 -m json.tool

if echo "$RESULT" | grep -q vietqr_url; then
  echo ""
  echo "OK: VietQR URLs generated"
else
  echo ""
  echo "FAIL: No vietqr_url in finalize response"
  exit 1
fi

echo ""
echo "=== All checks passed ==="
echo "Open $BASE_URL in browser (useLiveAgents: true in config.js)"
