import os

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val not in (None, "") else default


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


# --- moomoo OpenD connection -------------------------------------------------
OPEND_HOST = os.environ.get("OPEND_HOST", "127.0.0.1")
OPEND_PORT = _int("OPEND_PORT", 11111)
ACC_INDEX = _int("ACC_INDEX", 0)
# Precise account override -- run list_accounts.py to find the right acc_id
# if orders get rejected with "Account does not support trading X". Leave at
# 0 to fall back to ACC_INDEX (picks the Nth account in the filtered list,
# which is not necessarily the one approved for options).
ACC_ID = _int("ACC_ID", 0)

# "SIMULATE" (paper) or "REAL" (live money) -- start on SIMULATE, always.
TRADING_MODE = os.environ.get("TRADING_MODE", "SIMULATE").upper()
# Only used when TRADING_MODE=REAL. Never put this in source control.
TRADE_UNLOCK_PASSWORD = os.environ.get("TRADE_UNLOCK_PASSWORD", "")

# --- contract & sizing --------------------------------------------------------
# The exact moomoo contract code, e.g. "US.AMD260116C00150000".
# Leave blank to have contract_selector.py resolve one dynamically at startup
# instead (nearest expiry within [MIN_DTE_DAYS, MAX_DTE_DAYS], strike closest
# to the underlying's current price). Setting this manually always wins.
OPTION_CODE = os.environ.get("OPTION_CODE", "")

# --- dynamic contract resolution (only used when OPTION_CODE is blank) --------
# The underlying to trade options on.
UNDERLYING = os.environ.get("UNDERLYING", "US.AMD")
# "CALL" or "PUT" to force a side. Leave blank to ask StockV3Recommender's
# rules engine (OptionOperation.md-based) for the current bias each run --
# see direction.py. If it has no actionable signal, the bot refuses to start
# rather than guess a direction.
OPTION_TYPE = os.environ.get("OPTION_TYPE", "").upper()
# Nearest eligible expiry must be at least this many days out -- avoids 0DTE
# gamma/theta risk during the buy-hold-sell window this bot needs.
MIN_DTE_DAYS = _int("MIN_DTE_DAYS", 1)
# ...and at most this many days out ("within a week").
MAX_DTE_DAYS = _int("MAX_DTE_DAYS", 7)
# Base URL of the StockV3Recommender API (./server.sh start in that project),
# used to resolve OPTION_TYPE when it's left blank.
RECOMMENDER_URL = os.environ.get("RECOMMENDER_URL", "http://localhost:8000")

QTY = _int("QTY", 1)  # contracts per round trip

# --- pricing ------------------------------------------------------------------
# The option's minimum price increment. Set this to what you actually observe
# for this specific contract -- US options are commonly $0.01 (Penny Pilot,
# premium < $3) or $0.05 (premium >= $3, or non-Penny-Pilot names). The API
# does not reliably expose this, so it is a manual input -- get it wrong and
# every order gets rejected or rounded by the exchange.
STEP_SIZE = _float("STEP_SIZE", 0.05)
# How many ticks to improve on the touch by: buy at bid + NUM_STEPS*STEP_SIZE,
# sell at ask - NUM_STEPS*STEP_SIZE.
NUM_STEPS = _int("NUM_STEPS", 1)
# Only enter a new round trip if the quoted spread is at least this wide --
# otherwise there's no edge left to harvest after crossing NUM_STEPS ticks
# on each side.
MIN_SPREAD_TO_ENTER = _float("MIN_SPREAD_TO_ENTER", 0.20)

# --- timing / risk management --------------------------------------------------
# moomoo rate-limits order_list_query to 10 calls per 30 seconds; the bot
# calls it once per poll while watching an order, so this must stay above
# 3s (30/10) -- 4s leaves comfortable margin.
POLL_INTERVAL_SECONDS = _float("POLL_INTERVAL_SECONDS", 4.0)
# If the buy leg hasn't filled at all within this long, cancel and reassess.
BUY_TIMEOUT_SECONDS = _float("BUY_TIMEOUT_SECONDS", 60.0)
# If the sell leg hasn't filled within this long, reprice it one step closer
# to the bid to improve fill odds.
SELL_REPRICE_AFTER_SECONDS = _float("SELL_REPRICE_AFTER_SECONDS", 30.0)
SELL_REPRICE_STEP_TICKS = _int("SELL_REPRICE_STEP_TICKS", 1)
# After this many reprices, stop chasing and cross the spread (sell AT the
# current bid) to force an exit rather than sit on open-ended directional
# exposure indefinitely. This can lock in a small loss -- that is the point:
# a bounded, known loss beats an unbounded, unmanaged one.
MAX_SELL_REPRICES = _int("MAX_SELL_REPRICES", 5)

# Stop the bot (cleanly, canceling any open order) after this many
# CONSECUTIVE failed ticks, instead of retrying forever and needing a
# manual Ctrl+C. Resets to 0 on any successful tick.
MAX_CONSECUTIVE_ERRORS = _int("MAX_CONSECUTIVE_ERRORS", 5)

DB_PATH = os.environ.get("DB_PATH", "trades.db")
