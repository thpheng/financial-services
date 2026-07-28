# Stock Value Tracker

A small standalone web app for tracking the live value of stock holdings.
Enter a ticker and share count; it fetches the current price and shows
per-holding and total portfolio value.

## Run it

No build step or server required — just open `index.html` in a browser:

```
open index.html          # macOS
xdg-open index.html       # Linux
```

Or serve it locally (needed if your browser blocks `fetch` from `file://`):

```
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Data source

Quotes come from Yahoo Finance's public chart endpoint
(`query1.finance.yahoo.com/v8/finance/chart/<symbol>`) — no API key needed.
It's an unofficial/undocumented endpoint, so:

- It can rate-limit or occasionally block requests. If quotes stop loading,
  wait a bit and hit **Refresh All**.
- If Yahoo changes or blocks the endpoint entirely, swap `QUOTE_URL` in
  `app.js` for a keyed provider (e.g. Alpha Vantage, Finnhub, Twelve Data)
  and add the API key to the request.

## Features

- Add/remove holdings by ticker + share count
- Per-holding price, previous close, day change ($/%), and value
- Total portfolio value and total day change
- Manual refresh and optional 60s auto-refresh
- Holdings persist in `localStorage` between visits

## Files

- `index.html` — markup
- `style.css` — styling (light/dark aware)
- `app.js` — fetch logic, state, rendering
