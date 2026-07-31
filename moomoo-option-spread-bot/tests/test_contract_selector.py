import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from contract_selector import select_expiry, select_strike


def _expiry(dte, date=""):
    return {"strike_time": date or f"2026-08-{dte:02d}", "option_expiry_date_distance": dte}


def test_select_expiry_picks_nearest_within_window():
    expirations = [_expiry(0), _expiry(3), _expiry(7), _expiry(14)]
    picked = select_expiry(expirations, min_dte_days=1, max_dte_days=7)
    assert picked["option_expiry_date_distance"] == 3


def test_select_expiry_excludes_0dte_by_default_window():
    expirations = [_expiry(0), _expiry(10)]
    with pytest.raises(RuntimeError, match="no expiry between"):
        select_expiry(expirations, min_dte_days=1, max_dte_days=7)


def test_select_expiry_boundary_inclusive():
    expirations = [_expiry(1), _expiry(7), _expiry(8)]
    picked = select_expiry(expirations, min_dte_days=1, max_dte_days=7)
    assert picked["option_expiry_date_distance"] == 1

    picked_max = select_expiry([_expiry(7)], min_dte_days=1, max_dte_days=7)
    assert picked_max["option_expiry_date_distance"] == 7


def test_select_expiry_raises_when_none_eligible():
    with pytest.raises(RuntimeError, match="nearest available is 30 days out"):
        select_expiry([_expiry(30)], min_dte_days=1, max_dte_days=7)


def _contract(strike, code=None):
    return {"code": code or f"US.AMD260101C{int(strike * 1000):08d}", "strike_price": strike}


def test_select_strike_picks_closest_to_spot():
    chain = [_contract(160), _contract(165), _contract(170)]
    picked = select_strike(chain, spot=166.4, option_type="CALL", expiry="2026-08-07")
    assert picked["strike_price"] == 165


def test_select_strike_exact_match():
    chain = [_contract(160), _contract(165)]
    picked = select_strike(chain, spot=165.0, option_type="CALL", expiry="2026-08-07")
    assert picked["strike_price"] == 165


def test_select_strike_raises_on_empty_chain():
    with pytest.raises(RuntimeError, match="no CALL contracts found"):
        select_strike([], spot=165.0, option_type="CALL", expiry="2026-08-07")
