"""Resolves which exact option contract to trade: the nearest expiry within
[MIN_DTE_DAYS, MAX_DTE_DAYS] days out, then the strike closest to the
underlying's current price (ATM). Runs once at startup against a short-lived
quote connection -- the bot doesn't switch contracts mid-run; restart it to
pick up a new one (e.g. after this week's expiry).

The picking logic (select_expiry/select_strike) works on plain dicts so it
can be unit tested without a live OpenD connection, the same way
strategy.py is tested against a fake broker instead of the real one.
"""
from futu import OpenQuoteContext, RET_OK


def select_expiry(expirations: list, min_dte_days: int, max_dte_days: int) -> dict:
    eligible = [
        e for e in expirations
        if min_dte_days <= e["option_expiry_date_distance"] <= max_dte_days
    ]
    if not eligible:
        nearest = min((e["option_expiry_date_distance"] for e in expirations), default=None)
        raise RuntimeError(
            f"no expiry between {min_dte_days} and {max_dte_days} DTE -- "
            f"nearest available is {nearest} days out"
        )
    return min(eligible, key=lambda e: e["option_expiry_date_distance"])


def select_strike(chain: list, spot: float, option_type: str, expiry: str) -> dict:
    if not chain:
        raise RuntimeError(f"no {option_type} contracts found expiring {expiry}")
    return min(chain, key=lambda c: abs(c["strike_price"] - spot))


def resolve_atm_contract(host: str, port: int, underlying: str, option_type: str,
                          min_dte_days: int, max_dte_days: int) -> tuple:
    """Returns (code, expiry, strike, dte)."""
    quote_ctx = OpenQuoteContext(host=host, port=port)
    try:
        ret, expirations = quote_ctx.get_option_expiration_date(code=underlying)
        if ret != RET_OK:
            raise RuntimeError(f"get_option_expiration_date failed: {expirations}")
        nearest = select_expiry(expirations.to_dict("records"), min_dte_days, max_dte_days)
        expiry = nearest["strike_time"]
        dte = int(nearest["option_expiry_date_distance"])

        ret, snapshot = quote_ctx.get_market_snapshot([underlying])
        if ret != RET_OK:
            raise RuntimeError(f"get_market_snapshot failed: {snapshot}")
        spot = float(snapshot.iloc[0]["last_price"])

        ret, chain = quote_ctx.get_option_chain(
            code=underlying, start=expiry, end=expiry, option_type=option_type,
        )
        if ret != RET_OK:
            raise RuntimeError(f"get_option_chain failed: {chain}")
        best = select_strike(chain.to_dict("records"), spot, option_type, expiry)

        return str(best["code"]), str(expiry), float(best["strike_price"]), dte
    finally:
        quote_ctx.close()
