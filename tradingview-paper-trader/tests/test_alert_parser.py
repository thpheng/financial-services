import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alert_parser import AlertError, parse_alert  # noqa: E402

SECRET = "s3cr3t"


def base_payload(**overrides):
    payload = {"secret": SECRET, "ticker": "AAPL", "action": "buy", "qty": 10}
    payload.update(overrides)
    return payload


def test_valid_market_buy():
    order = parse_alert(base_payload(), SECRET, default_qty=1, max_qty=1000)
    assert order.symbol == "AAPL"
    assert order.side == "BUY"
    assert order.qty == 10
    assert order.order_type == "MARKET"


def test_symbol_lowercase_is_normalized():
    order = parse_alert(base_payload(ticker="aapl"), SECRET, default_qty=1, max_qty=1000)
    assert order.symbol == "AAPL"


def test_wrong_secret_rejected():
    with pytest.raises(AlertError, match="secret"):
        parse_alert(base_payload(secret="nope"), SECRET, default_qty=1, max_qty=1000)


def test_missing_secret_rejected():
    payload = base_payload()
    del payload["secret"]
    with pytest.raises(AlertError, match="secret"):
        parse_alert(payload, SECRET, default_qty=1, max_qty=1000)


def test_missing_ticker_rejected():
    payload = base_payload()
    del payload["ticker"]
    with pytest.raises(AlertError, match="ticker"):
        parse_alert(payload, SECRET, default_qty=1, max_qty=1000)


def test_symbol_field_alias_accepted():
    payload = base_payload()
    del payload["ticker"]
    payload["symbol"] = "MSFT"
    order = parse_alert(payload, SECRET, default_qty=1, max_qty=1000)
    assert order.symbol == "MSFT"


@pytest.mark.parametrize("action,expected_side", [
    ("buy", "BUY"),
    ("long", "BUY"),
    ("sell", "SELL"),
    ("exit_long", "SELL"),
    ("short", "SELL_SHORT"),
    ("buy_to_cover", "BUY_BACK"),
    ("exit_short", "BUY_BACK"),
    ("BUY", "BUY"),
])
def test_action_side_mapping(action, expected_side):
    order = parse_alert(base_payload(action=action), SECRET, default_qty=1, max_qty=1000)
    assert order.side == expected_side


def test_unknown_action_rejected():
    with pytest.raises(AlertError, match="action"):
        parse_alert(base_payload(action="yolo"), SECRET, default_qty=1, max_qty=1000)


def test_default_qty_used_when_omitted():
    payload = base_payload()
    del payload["qty"]
    order = parse_alert(payload, SECRET, default_qty=7, max_qty=1000)
    assert order.qty == 7


def test_contracts_alias_for_qty():
    payload = base_payload()
    del payload["qty"]
    payload["contracts"] = 3
    order = parse_alert(payload, SECRET, default_qty=1, max_qty=1000)
    assert order.qty == 3


def test_zero_qty_rejected():
    with pytest.raises(AlertError, match="positive"):
        parse_alert(base_payload(qty=0), SECRET, default_qty=1, max_qty=1000)


def test_negative_qty_rejected():
    with pytest.raises(AlertError, match="positive"):
        parse_alert(base_payload(qty=-5), SECRET, default_qty=1, max_qty=1000)


def test_qty_over_max_rejected():
    with pytest.raises(AlertError, match="max_qty"):
        parse_alert(base_payload(qty=999), SECRET, default_qty=1, max_qty=100)


def test_non_numeric_qty_rejected():
    with pytest.raises(AlertError, match="numeric"):
        parse_alert(base_payload(qty="lots"), SECRET, default_qty=1, max_qty=1000)


def test_limit_order_requires_price():
    with pytest.raises(AlertError, match="price"):
        parse_alert(base_payload(order_type="limit"), SECRET, default_qty=1, max_qty=1000)


def test_limit_order_with_price():
    order = parse_alert(
        base_payload(order_type="limit", price=150.25), SECRET, default_qty=1, max_qty=1000
    )
    assert order.order_type == "NORMAL"
    assert order.price == 150.25


def test_limit_order_negative_price_rejected():
    with pytest.raises(AlertError, match="positive"):
        parse_alert(
            base_payload(order_type="limit", price=-5), SECRET, default_qty=1, max_qty=1000
        )


def test_market_order_price_optional_defaults_zero():
    order = parse_alert(base_payload(), SECRET, default_qty=1, max_qty=1000)
    assert order.price == 0.0


def test_market_order_uses_reference_price_if_given():
    order = parse_alert(base_payload(price=201.5), SECRET, default_qty=1, max_qty=1000)
    assert order.price == 201.5


def test_unsupported_order_type_rejected():
    with pytest.raises(AlertError, match="order_type"):
        parse_alert(base_payload(order_type="stop"), SECRET, default_qty=1, max_qty=1000)


def test_non_dict_payload_rejected():
    with pytest.raises(AlertError, match="JSON object"):
        parse_alert(["not", "a", "dict"], SECRET, default_qty=1, max_qty=1000)
