"""Asks StockV3Recommender's rules engine (OptionOperation.md-based) whether
the underlying is currently a Buy Call or Buy Put setup -- this bot doesn't
generate its own directional signal, it defers to that one so the two
projects don't drift apart. Only used when OPTION_TYPE is left blank in .env.

Scans `ticker` directly (via StockV3Recommender's `ticker` query param) so
this works for any ticker OpenD can quote, not just ones already listed in
that project's watchlist.txt.

When there's no actionable signal (No Trade / blocked), this does NOT refuse
to start -- it defaults to DEFAULT_OPTION_TYPE_ON_NO_SIGNAL and returns a
note explaining why, for main.py to log clearly. That default isn't backed
by a real signal, so it needs to stand out in the log for later review.
"""
from typing import Optional

import requests

STRATEGY_TO_OPTION_TYPE = {"Buy Call": "CALL", "Buy Put": "PUT"}
DEFAULT_OPTION_TYPE_ON_NO_SIGNAL = "CALL"


def find_ticker_result(results: list, ticker: str) -> Optional[dict]:
    return next((r for r in results if r.get("ticker") == ticker), None)


def map_strategy(strategy: str) -> str:
    option_type = STRATEGY_TO_OPTION_TYPE.get(strategy)
    if option_type is None:
        raise RuntimeError(f"unrecognized strategy {strategy!r} -- expected 'Buy Call' or 'Buy Put'")
    return option_type


def resolve_direction(ticker: str, recommender_url: str) -> tuple:
    """Returns (option_type, note). note is None when a real signal was
    found; otherwise it's a message explaining the fallback -- log it."""
    try:
        resp = requests.post(f"{recommender_url}/api/scan", params={"ticker": ticker}, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"could not reach StockV3Recommender at {recommender_url} ({e}) -- "
            f"is `./server.sh start` running in that project? Or set OPTION_TYPE "
            f"in .env to skip this and force a side."
        ) from e

    match = find_ticker_result(resp.json().get("results", []), ticker)
    if match is None:
        note = (
            f"StockV3Recommender has no actionable signal for {ticker} right now "
            f"(No Trade / blocked) -- defaulting to {DEFAULT_OPTION_TYPE_ON_NO_SIGNAL}, "
            f"not a real signal. Review this trade later; set OPTION_TYPE in .env "
            f"to override the default."
        )
        return DEFAULT_OPTION_TYPE_ON_NO_SIGNAL, note

    return map_strategy(match["strategy"]), None
