# TradingView &rarr; Moomoo Paper Trader

Receives TradingView **webhook alerts** and submits **paper trades** through
your moomoo (Futu) account. Trading environment is hardcoded to
`TrdEnv.SIMULATE` in `moomoo_client.py` — this app can never place a live
order, regardless of what a webhook payload says.

## Why this shape

TradingView has no public API to submit orders — the only supported way for
external code to react to a TradingView chart/strategy is a **webhook alert**:
you set a URL, TradingView POSTs a JSON body to it when the alert fires. This
app is that receiving server, and it turns the alert into a paper order via
moomoo's OpenAPI (the `futu-api` Python package talking to a local **OpenD**
gateway process).

```
TradingView alert  --POST-->  this Flask app  --futu-api-->  OpenD  --> moomoo paper account
```

## Prerequisites

1. A moomoo account with paper trading enabled (US market).
2. **moomoo OpenD** — the desktop gateway program — downloaded, running, and
   logged into your moomoo account. In OpenD's settings, note the API port
   (default `11111`) and make sure the API service is enabled.
   OpenD must keep running for this app to reach your account; it holds the
   authenticated session.
3. Python 3.9+.

## Setup

```bash
cd tradingview-paper-trader
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `OPEND_HOST` / `OPEND_PORT` — where OpenD is listening (defaults are right
  if OpenD runs on the same machine).
- `WEBHOOK_SECRET` — generate one with
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` and paste
  it in. TradingView alerts have no header/auth support, so this secret must
  travel inside the JSON body — treat it like a password.
- `DEFAULT_QTY`, `MAX_QTY` — fallback share count and a hard cap that rejects
  outsized orders before they reach the broker (fat-finger / bad-alert
  protection).

Run it:

```bash
python3 app.py
```

Visit `http://localhost:5000` for the dashboard (account balance, open
positions, moomoo order history, and a local webhook audit log).

## Wiring up TradingView

TradingView needs a **public HTTPS URL** to send the webhook to — it cannot
reach `localhost`. For testing, tunnel your local port:

```bash
ngrok http 5000
```

Then in TradingView: open your chart &rarr; **Alerts** &rarr; create alert &rarr;
check **Webhook URL** &rarr; paste `https://<your-ngrok-id>.ngrok.io/webhook/tradingview`.

In the alert's **Message** field, send JSON matching what `alert_parser.py`
expects:

```json
{
  "secret": "paste-your-WEBHOOK_SECRET-here",
  "ticker": "{{ticker}}",
  "action": "buy",
  "qty": 10,
  "order_type": "market"
}
```

- `action`: one of `buy`, `sell`, `long`, `short`, `exit_long`,
  `exit_short`, `buy_to_cover`, `sell_to_close`.
- `order_type`: `market` (default) or `limit` — `limit` requires a `price`
  field.
- For a Pine strategy alert, `{{strategy.order.action}}` gives `buy`/`sell`
  automatically and `{{strategy.order.contracts}}` gives the size (read as
  `qty`; `contracts` is also accepted as an alias).

Set up a separate alert (or alert condition) per side, since a single
webhook message is static text with placeholders, not conditional logic.

## Testing without TradingView or OpenD

```bash
pytest tests/            # pure parsing/validation logic, no network needed
```

To test the whole webhook path once OpenD is running:

```bash
curl -X POST http://localhost:5000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"<your secret>","ticker":"AAPL","action":"buy","qty":1}'
```

## Safety notes

- **`trd_env` is hardcoded to `SIMULATE`** in `moomoo_client.py` — not
  read from the request — so a leaked secret or a bad payload cannot trigger
  a real trade.
- `MAX_QTY` in `.env` is a second backstop against a malformed or spoofed
  alert submitting an absurd order size.
- Duplicate webhook deliveries (TradingView retries on timeout) with an
  identical body within 60 seconds are detected by hash and skipped — check
  `store.DEDUPE_WINDOW_SECONDS` if you need a different window.
- Every webhook — accepted, rejected, or errored — is logged to
  `trades.db` (`webhook_log` table) so you have an audit trail independent
  of moomoo's own order history.
- US-market paper trading via this API does not support pre/post-market or
  overnight sessions (a moomoo platform limitation, not this app's).
- Review moomoo/Futu's API terms for automated/unattended use before
  running this continuously in production.

## Files

- `app.py` — Flask app: webhook endpoint, dashboard, JSON API
- `alert_parser.py` — pure validation/parsing of the TradingView payload (unit tested)
- `moomoo_client.py` — futu-api wrapper, hardcoded to paper trading
- `store.py` — SQLite webhook audit log + dedupe
- `config.py` — environment configuration
- `templates/dashboard.html` — account/positions/orders/log dashboard
- `tests/test_alert_parser.py` — 28 tests covering the parsing/validation logic
