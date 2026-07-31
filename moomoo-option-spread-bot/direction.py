"""Asks StockV3Recommender's rules engine (OptionOperation.md-based) whether
the underlying is currently a Buy Call or Buy Put setup -- this bot doesn't
generate its own directional signal, it defers to that one so the two
projects don't drift apart. Only used when OPTION_TYPE is left blank in .env.
"""
from typing import Optional

import requests

STRATEGY_TO_OPTION_TYPE = {"Buy Call": "CALL", "Buy Put": "PUT"}


def find_ticker_result(results: list, ticker: str) -> Optional[dict]:
    return next((r for r in results if r.get("ticker") == ticker), None)


def map_strategy(strategy: str) -> str:
    option_type = STRATEGY_TO_OPTION_TYPE.get(strategy)
    if option_type is None:
        raise RuntimeError(f"unrecognized strategy {strategy!r} -- expected 'Buy Call' or 'Buy Put'")
    return option_type


def resolve_direction(ticker: str, recommender_url: str) -> str:
    try:
        resp = requests.post(f"{recommender_url}/api/scan", timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"could not reach StockV3Recommender at {recommender_url} ({e}) -- "
            f"is `./server.sh start` running in that project? Or set OPTION_TYPE "
            f"in .env to skip this and force a side."
        ) from e

    match = find_ticker_result(resp.json().get("results", []), ticker)
    if match is None:
        raise RuntimeError(
            f"StockV3Recommender has no actionable signal for {ticker} right now "
            f"(No Trade / blocked) -- not entering a directional position blind. "
            f"Check {recommender_url} or set OPTION_TYPE in .env to force a side."
        )
    return map_strategy(match["strategy"])
