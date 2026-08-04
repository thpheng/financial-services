import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import requests

from direction import DEFAULT_OPTION_TYPE_ON_NO_SIGNAL, find_ticker_result, map_strategy, resolve_direction


def test_find_ticker_result_matches():
    results = [{"ticker": "SPY", "strategy": "Buy Put"}, {"ticker": "AMD", "strategy": "Buy Call"}]
    assert find_ticker_result(results, "AMD") == {"ticker": "AMD", "strategy": "Buy Call"}


def test_find_ticker_result_no_match_returns_none():
    assert find_ticker_result([{"ticker": "SPY", "strategy": "Buy Put"}], "AMD") is None


def test_map_strategy_call():
    assert map_strategy("Buy Call") == "CALL"


def test_map_strategy_put():
    assert map_strategy("Buy Put") == "PUT"


def test_map_strategy_unrecognized_raises():
    with pytest.raises(RuntimeError, match="unrecognized strategy"):
        map_strategy("No Trade")


def _fake_response(json_body):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value=json_body)
    return resp


def test_resolve_direction_returns_option_type_for_actionable_signal():
    body = {"results": [{"ticker": "AMD", "strategy": "Buy Call"}]}
    with patch("direction.requests.post", return_value=_fake_response(body)) as post:
        option_type, note = resolve_direction("AMD", "http://localhost:8000")
    assert option_type == "CALL"
    assert note is None
    post.assert_called_once_with(
        "http://localhost:8000/api/scan", params={"ticker": "AMD"}, timeout=30
    )


def test_resolve_direction_defaults_with_note_when_no_actionable_signal():
    # server scanned the ticker (per the `ticker` param) but it came back "No
    # Trade", which the /scan route filters out of `results` entirely
    body = {"results": []}
    with patch("direction.requests.post", return_value=_fake_response(body)):
        option_type, note = resolve_direction("AMD", "http://localhost:8000")
    assert option_type == DEFAULT_OPTION_TYPE_ON_NO_SIGNAL
    assert note is not None
    assert "AMD" in note and "no actionable signal" in note


def test_resolve_direction_raises_clearly_when_recommender_unreachable():
    with patch("direction.requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(RuntimeError, match="could not reach StockV3Recommender"):
            resolve_direction("AMD", "http://localhost:8000")
