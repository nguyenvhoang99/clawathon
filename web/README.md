# Team Trip Website — Zalopay

Giao diện 3 cột tiếng Việt: thời tiết · lên kế hoạch · chia hóa đơn.

## Bảng màu

| Loại | Màu |
|------|-----|
| Chính | `#ffffff`, `#00cf6a`, `#0033c9` |
| Phụ | `#00b4ff`, `#a1ff00`, `#6f0cdf`, `#fd7290`, `#f8a000` |

Thương hiệu: **Zalopay** (không viết ZaloPay).

## Layout

| Column | Content |
|--------|---------|
| **Left** | Weather chat + 7-day forecast (Hanoi, Ho Chi Minh, Da Nang) |
| **Center** | Team trip planner + ZaloPay booking chips |
| **Right** | Bill splitter — expandable panel (ZaloPay wallet / phone) |

Progressive disclosure: collapsed bill summary by default; expand for members, expenses, settle.

## Quick start (demo mode)

Weather slider uses **live Open-Meteo**. Trip and bill use mock data until live mode is enabled.

```bash
cd web
python3 -m http.server 3000
```

Open http://127.0.0.1:3000

## Live agent mode

### 1. Configure

```bash
cd web
cp config.example.js config.js
```

Edit `config.js`:

- `useLiveAgents: true`
- `zalopay.bankBin: "<your-napas-bin>"` — required for VietQR settlement to ZaloPay wallets

### 2. Run everything (proxy + verification)

```bash
bash web/scripts/run_live.sh
```

This starts `proxy.py`, runs API smoke tests (weather, trip, bill with ZaloPay phones), then keeps the server running at http://127.0.0.1:3000.

### 3. API-only verification (proxy must already be running)

```bash
cd web && python3 proxy.py &
bash web/scripts/verify_live.sh
```

### 4. Direct bill-splitter runtime (ZaloPay phones)

```bash
export ZALOPAY_BIN="<your-napas-bin>"
bash agents/bill-splitter/scripts/demo_smoke_zalopay.sh
```

## ZaloPay integration

| Feature | Behavior |
|---------|----------|
| **Trip booking** | ZaloPay-branded chips (Vietjet, FUTA, hotels) — UI links, no payment API |
| **Bill settlement** | Phone number = `account_no`, `bank_bin` from config, `bank_code: ZLP` |
| **Member registration** | Web form or API `register_member` with ZaloPay wallet fields |

## Proxy routes

| Route | Agent |
|-------|-------|
| `POST /api/weather` | weather-chatbot |
| `POST /api/trip` | trip-planner |
| `POST /api/bill` | bill-splitter |

Headers: `X-GreenNode-AgentBase-Custom-Team-Id`, `X-GreenNode-AgentBase-Session-Id`, `X-GreenNode-AgentBase-User-Id`

## Files

| File | Purpose |
|------|---------|
| `index.html` | 3-column UI |
| `config.example.js` | Agent URLs + ZaloPay settings |
| `config.js` | Local config (gitignored) |
| `proxy.py` | Static server + CORS proxy |
| `scripts/run_live.sh` | Start live mode + verify |
| `scripts/verify_live.sh` | Curl E2E through proxy |
