"""Pure parsing/validation of a TradingView webhook alert into an order request.

No network or SDK calls happen here — this is deliberately side-effect-free
so it can be unit tested without OpenD or a moomoo account.
"""
import hmac
from dataclasses import dataclass
from typing import Optional

SIDE_MAP = {
    "buy": "BUY",
    "long": "BUY",
    "sell": "SELL",
    "exit_long": "SELL",
    "sell_to_close": "SELL",
    "short": "SELL_SHORT",
    "buy_to_cover": "BUY_BACK",
    "exit_short": "BUY_BACK",
}

ORDER_TYPE_MAP = {
    "market": "MARKET",
    "limit": "NORMAL",
    "normal": "NORMAL",
}


class AlertError(ValueError):
    """Raised when a webhook payload is malformed or fails validation."""


@dataclass(frozen=True)
class AlertOrder:
    symbol: str
    side: str
    qty: int
    order_type: str
    price: float


def parse_alert(payload: dict, expected_secret: str, default_qty: int, max_qty: int) -> AlertOrder:
    if not isinstance(payload, dict):
        raise AlertError("payload must be a JSON object")

    got_secret = str(payload.get("secret", ""))
    if not expected_secret or not hmac.compare_digest(got_secret, expected_secret):
        raise AlertError("invalid or missing 'secret'")

    ticker = payload.get("ticker") or payload.get("symbol")
    if not ticker or not str(ticker).strip():
        raise AlertError("missing 'ticker'")
    symbol = str(ticker).strip().upper()

    action = str(payload.get("action", "")).strip().lower()
    if action not in SIDE_MAP:
        raise AlertError(
            f"unrecognized 'action' {action!r} — expected one of {sorted(SIDE_MAP)}"
        )
    side = SIDE_MAP[action]

    qty_raw = payload.get("qty", payload.get("contracts", default_qty))
    try:
        qty = int(float(qty_raw))
    except (TypeError, ValueError):
        raise AlertError(f"'qty' must be numeric, got {qty_raw!r}")
    if qty <= 0:
        raise AlertError("'qty' must be positive")
    if qty > max_qty:
        raise AlertError(f"'qty' {qty} exceeds max_qty {max_qty}")

    order_type_raw = str(payload.get("order_type", "market")).strip().lower()
    if order_type_raw not in ORDER_TYPE_MAP:
        raise AlertError(f"unsupported 'order_type' {order_type_raw!r}")
    order_type = ORDER_TYPE_MAP[order_type_raw]

    price_raw: Optional[object] = payload.get("price")
    if order_type == "NORMAL":
        if price_raw is None:
            raise AlertError("'price' is required for limit ('order_type': 'limit') orders")
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            raise AlertError(f"'price' must be numeric, got {price_raw!r}")
        if price <= 0:
            raise AlertError("'price' must be positive")
    else:
        # MARKET orders still send a reference price to the API (it does not
        # act as a limit); fall back to 0 if the alert didn't include one
        # (e.g. no {{close}} placeholder in the TradingView message).
        try:
            price = float(price_raw) if price_raw is not None else 0.0
        except (TypeError, ValueError):
            price = 0.0

    return AlertOrder(symbol=symbol, side=side, qty=qty, order_type=order_type, price=price)
