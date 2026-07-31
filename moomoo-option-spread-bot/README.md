# Moomoo Option Spread-Capture Bot

Buys an option a few ticks above the bid, waits for the fill, then sells a
few ticks below the ask -- harvesting part of the quoted bid/ask spread
instead of paying it as a taker. Runs entirely against moomoo's own API
(OpenD) -- no TradingView, no webhooks, nothing internet-facing.

```
your Mac
 ├─ moomoo OpenD (desktop app, logged in)
 └─ this bot (Python loop):
     1. reads live bid/ask for one option contract
     2. if the spread is wide enough: buy at bid + N ticks
     3. wait for the fill
     4. sell (the position just bought) at ask - N ticks
     5. if the sell doesn't fill in time, reprice it closer to the bid;
        after too many reprices, cross the spread to force an exit
     6. log the round trip, go back to step 1
```

## Why buy-then-sell, not both at once

Resting a buy and a sell on the *same contract* from the *same account*
simultaneously risks tripping self-match/wash-trade prevention on some
venues, and if both fill at the same price you've captured zero edge before
fees. Sequencing removes both problems -- the tradeoff is you hold a real
position (with real directional risk) in the window between the buy filling
and the sell filling. That's what the reprice/force-exit logic in
`strategy.py` is for: it won't let that window stay open indefinitely.

## Setup on a Mac (no cloud server needed)

1. Download **moomoo OpenD** for macOS from moomoo's OpenAPI page and log in
   normally through its GUI (2FA approval arrives as a push notification in
   the moomoo iPhone app). Note the API port shown in OpenD's settings
   (default `11111`).
2. Keep the Mac from sleeping while the bot runs -- either disable sleep in
   System Settings > Battery > Options, or just run the bot under
   `caffeinate`:
   ```bash
   caffeinate -di python3 main.py
   ```
   If the Mac sleeps, loses wifi, or OpenD's session drops, the bot simply
   stops watching the market until you notice and restart it -- there's no
   automatic recovery built in yet.
3. ```bash
   cd moomoo-option-spread-bot
   pip install -r requirements.txt
   cp .env.example .env
   ```
4. Pick a contract. Either:
   - **Manually**: look up the exact code (don't hand-type an OCC string yourself):
     ```bash
     python3 find_option_code.py US.AMD 2026-01-16
     ```
     Copy the `code` column value for the strike you want into `OPTION_CODE` in `.env`.
   - **Dynamically** (default -- leave `OPTION_CODE` blank): at startup the bot
     picks the nearest expiry within `MIN_DTE_DAYS`-`MAX_DTE_DAYS` days out and
     the strike closest to the underlying's current price (ATM). See
     "Dynamic contract selection" below for how CALL vs PUT gets decided.
5. Set `STEP_SIZE` in `.env` to the **real** minimum price increment for
   that contract (watch its quote for a few minutes -- if consecutive
   quoted prices move in $0.05 jumps, that's your step; US options are
   commonly $0.01 or $0.05 depending on premium and program). Get this
   wrong and orders get rejected or rounded by the exchange.
6. Leave `TRADING_MODE=SIMULATE` and run it:
   ```bash
   python3 main.py
   ```

## Dynamic contract selection

When `OPTION_CODE` is left blank in `.env`, `main.py` resolves one fresh
each time the bot starts (once, not per-poll -- restart to pick a new
contract, e.g. after this week's expiry rolls):

1. **Side (CALL/PUT)**: if `OPTION_TYPE` is set in `.env`, that wins.
   Otherwise `direction.py` calls `StockV3Recommender`'s `/api/scan` endpoint
   (the sibling project's OptionOperation.md-based rules engine) for
   `UNDERLYING`'s current bias. If it comes back "No Trade" or blocked
   (outside entry window, VIX too high, etc.), the bot refuses to start
   rather than guess a side -- this bot doesn't generate its own
   directional signal, it only executes.
2. **Contract**: `contract_selector.py` asks OpenD for `UNDERLYING`'s
   expirations, picks the nearest one within `[MIN_DTE_DAYS, MAX_DTE_DAYS]`
   days out, then the strike closest to the underlying's live price (ATM).

Requires `StockV3Recommender` running (`cd ../../StockV3Recommender &&
./server.sh start`, default `http://localhost:8000`) whenever `OPTION_TYPE`
is left blank for auto-direction.

## Testing without OpenD or a market connection

```bash
pytest tests/    # state-machine logic against a fake in-memory broker
```

These 10 tests cover: entering only when the spread is wide enough, correct
buy/sell pricing, buy timeout with zero and partial fills, sell repricing
toward the bid, the forced-exit-at-max-reprices fallback, and the price
floor (never repricing below the current bid). None of them touch OpenD --
they verify the decision logic, not the connection to moomoo.

## Switching paper -> real

Change two things in `.env`, nothing in the code:

```
TRADING_MODE=REAL
TRADE_UNLOCK_PASSWORD=<your moomoo trade password>
```

Real orders require unlocking (`unlock_trade`) before they'll submit --
paper trading doesn't need this, so `MoomooBrokerClient` only calls it when
`TRADING_MODE=REAL`, and refuses to start in REAL mode without a password
set (see `moomoo_client.py`). There's no other gate — treat flipping this
env var with the seriousness of flipping on real order flow, because that's
exactly what it does.

Before flipping it: run in SIMULATE for a real stretch of market hours first
and look at `trades.db` (`store.summary()` / `store.recent()`) to see
whether the strategy is actually netting positive `captured_edge`, and how
often it's hitting `forced_exit` (a high forced-exit rate means the spread
usually isn't there by the time the sell leg is ready, i.e. the strategy
isn't working as hoped).

## Trade log for backtesting/analysis (`trades.db`)

Two tables, both written live as the bot runs:

- `round_trips` -- one row per completed/aborted buy→sell cycle (outcome):
  `buy_price`, `sell_price`, `captured_edge`, `forced_exit`.
- `order_events` -- one row per order action (what actually got submitted):
  every `SUBMIT` (buy or sell), `REPRICE`, `FORCE_EXIT`, and `CANCEL` (buy
  timing out unfilled), with the order's price/qty and the live bid/ask at
  that moment. `trip_seq` is shared between a round trip and the order
  events that produced it, so you can join the two, e.g. to see how many
  reprices or cancelled entry attempts preceded a given outcome.

`store.recent_order_events(path, limit=100)` reads the latter back; `main.py`
also logs every event at INFO level as it happens (`order SUBMIT BUY ...`).

## "Get Order list request failed due to high frequency"

moomoo rate-limits `order_list_query` to 10 calls per 30 seconds. The bot
calls it once per poll while watching an open order, so `POLL_INTERVAL_SECONDS`
must stay above 3 -- the default is 4 for margin. If you lower it and see
this error, raise it back up.

## "Account does not support trading X"

moomoo accounts can have multiple sub-accounts (e.g. a general simulated
account vs. one specifically approved for options), and `ACC_INDEX=0` just
grabs whichever one the API lists first -- not necessarily the right one.
If an order gets rejected with this error, run:
```bash
python3 list_accounts.py
```
It lists every account visible to your login with its `trd_env`,
`sim_acc_type`, and `trdmarket_auth` (what it's actually approved to
trade). Put the correct one's `acc_id` in `ACC_ID` in `.env` -- that
targets it precisely instead of relying on list order.

## If the bot stops itself with "N consecutive errors"

That's `MAX_CONSECUTIVE_ERRORS` in `.env` (default 5) doing its job --
rather than retry a broken order forever and need a manual Ctrl+C, the bot
cancels any open order and exits cleanly after that many back-to-back
failed polls. Scroll up in the terminal to the first traceback (not just
the last one) to see the actual root cause, fix it, then restart.

## Tuning knobs (all in `.env`)

| Variable | What it controls |
|---|---|
| `NUM_STEPS` | How many ticks better than the touch to quote (1 or 2, per your ask) |
| `MIN_SPREAD_TO_ENTER` | Skip entries where there's no real edge left after crossing both sides |
| `BUY_TIMEOUT_SECONDS` | How long to wait for the buy to fill before giving up |
| `SELL_REPRICE_AFTER_SECONDS` / `SELL_REPRICE_STEP_TICKS` | How aggressively to chase a fill on the sell leg |
| `MAX_SELL_REPRICES` | When to stop chasing and force an exit at the bid instead |
| `UNDERLYING` | Underlying to trade options on (dynamic selection only) |
| `OPTION_TYPE` | Force CALL or PUT; blank = ask StockV3Recommender each run |
| `MIN_DTE_DAYS` / `MAX_DTE_DAYS` | Eligible expiry window for dynamic selection |
| `RECOMMENDER_URL` | Where to reach StockV3Recommender's API |

## Files

- `main.py` -- connects to OpenD, runs the poll loop, handles shutdown (cancels any open order)
- `strategy.py` -- the state machine (`SpreadCaptureBot`), pure logic, unit tested
- `moomoo_client.py` -- the only file that imports `futu`; wraps OpenD quote/trade calls
- `store.py` -- SQLite round-trip + order-event log, summary stats
- `find_option_code.py` -- looks up the exact contract code for an underlying + expiry (manual path)
- `contract_selector.py` -- dynamic path: nearest-expiry, closest-to-spot contract selection
- `direction.py` -- dynamic path: asks StockV3Recommender for CALL/PUT bias
- `tests/test_strategy.py` -- 10 tests against a fake in-memory broker
- `tests/test_contract_selector.py`, `tests/test_direction.py` -- pure-logic tests for the dynamic path
