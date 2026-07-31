import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from moomoo_client import OrderStatus
from strategy import RoundTrip, SpreadCaptureBot, State


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeBroker:
    """In-memory stand-in for MoomooBrokerClient -- lets the state machine be
    tested without a real OpenD connection."""

    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask
        self._orders = {}
        self._next_id = 1
        self.cancelled = []

    def get_bid_ask(self, code):
        return self.bid, self.ask

    def place_limit_order(self, code, side, qty, price):
        order_id = str(self._next_id)
        self._next_id += 1
        self._orders[order_id] = {
            "status": OrderStatus.SUBMITTED, "dealt_qty": 0.0, "price": price,
            "qty": qty, "side": side,
        }
        return order_id

    def get_order(self, order_id):
        from moomoo_client import Order
        o = self._orders[order_id]
        return Order(order_id=order_id, status=o["status"], dealt_qty=o["dealt_qty"], price=o["price"])

    def modify_order_price(self, order_id, qty, price):
        self._orders[order_id]["price"] = price

    def cancel_order(self, order_id):
        self._orders[order_id]["status"] = OrderStatus.CANCELLED_ALL
        self.cancelled.append(order_id)

    # -- test helpers, not part of the real interface --
    def fill(self, order_id, dealt_qty=None, price=None):
        o = self._orders[order_id]
        o["status"] = OrderStatus.FILLED_ALL
        o["dealt_qty"] = dealt_qty if dealt_qty is not None else o["qty"]
        if price is not None:
            o["price"] = price

    def partial_fill(self, order_id, dealt_qty):
        o = self._orders[order_id]
        o["status"] = OrderStatus.FILLED_PART
        o["dealt_qty"] = dealt_qty


def make_bot(broker, clock, **overrides):
    round_trips = []
    order_events = []
    defaults = dict(
        client=broker, code="US.AMD260116C00150000", qty=1, step_size=0.05, num_steps=1,
        min_spread_to_enter=0.20, buy_timeout_seconds=60, sell_reprice_after_seconds=30,
        sell_reprice_step_ticks=1, max_sell_reprices=3,
        on_round_trip=lambda rt: round_trips.append(rt),
        on_order_event=lambda evt: order_events.append(evt), now_fn=clock,
    )
    defaults.update(overrides)
    return SpreadCaptureBot(**defaults), round_trips, order_events


def test_stays_idle_when_spread_too_narrow():
    broker = FakeBroker(bid=1.00, ask=1.10)  # spread 0.10 < min 0.20
    bot, _, _ = make_bot(broker, FakeClock())
    bot.tick()
    assert bot.state == State.IDLE
    assert bot._buy_order_id is None


def test_enters_buy_with_correct_price_when_spread_wide():
    broker = FakeBroker(bid=1.00, ask=2.00)  # spread 1.00
    bot, _, _ = make_bot(broker, FakeClock())
    bot.tick()
    assert bot.state == State.BUY_WORKING
    order = broker.get_order(bot._buy_order_id)
    assert order.price == pytest.approx(1.05)  # bid + 1*0.05


def test_skips_entry_if_improved_price_would_cross_ask():
    broker = FakeBroker(bid=1.00, ask=1.02)  # spread 0.02 -- but min_spread gate catches this anyway
    bot, _, _ = make_bot(broker, FakeClock(), min_spread_to_enter=0.0, num_steps=10)
    bot.tick()
    # bid + 10*0.05 = 1.50 >= ask 1.02 -> must not enter
    assert bot.state == State.IDLE


def test_buy_fill_transitions_to_sell_with_price_from_current_ask():
    broker = FakeBroker(bid=1.00, ask=2.00)
    bot, _, _ = make_bot(broker, FakeClock())
    bot.tick()  # places buy at 1.05
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    broker.ask = 2.20  # market moved between buy fill and sell placement
    bot.tick()
    assert bot.state == State.SELL_WORKING
    sell_order = broker.get_order(bot._sell_order_id)
    assert sell_order.price == pytest.approx(2.15)  # new ask 2.20 - 1*0.05


def test_buy_timeout_with_zero_fill_cancels_and_returns_idle():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, _ = make_bot(broker, clock, buy_timeout_seconds=10)
    bot.tick()
    buy_id = bot._buy_order_id
    clock.advance(11)
    bot.tick()
    assert bot.state == State.IDLE
    assert buy_id in broker.cancelled


def test_buy_timeout_with_partial_fill_hedges_filled_qty():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, _ = make_bot(broker, clock, qty=5, buy_timeout_seconds=10)
    bot.tick()
    buy_id = bot._buy_order_id
    broker.partial_fill(buy_id, dealt_qty=2)
    clock.advance(11)
    bot.tick()
    assert buy_id in broker.cancelled
    assert bot.state == State.SELL_WORKING
    assert broker._orders[bot._sell_order_id]["qty"] == 2


def test_sell_fill_logs_round_trip_with_correct_edge():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, round_trips, _ = make_bot(broker, clock)
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()  # -> SELL_WORKING at 2.00 - 0.05 = 1.95
    broker.fill(bot._sell_order_id, dealt_qty=1, price=1.95)
    bot.tick()
    assert bot.state == State.IDLE
    assert len(round_trips) == 1
    rt = round_trips[0]
    assert rt.buy_price == pytest.approx(1.05)
    assert rt.sell_price == pytest.approx(1.95)
    assert rt.forced_exit is False


def test_sell_reprices_toward_bid_after_timeout():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, _ = make_bot(broker, clock, sell_reprice_after_seconds=30, sell_reprice_step_ticks=2)
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()  # SELL_WORKING at 1.95
    clock.advance(31)
    bot.tick()
    sell_order = broker.get_order(bot._sell_order_id)
    assert sell_order.price == pytest.approx(1.85)  # 1.95 - 2*0.05
    assert bot._sell_reprice_count == 1


def test_sell_force_exits_at_bid_after_max_reprices():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, round_trips, _ = make_bot(
        broker, clock, sell_reprice_after_seconds=10, max_sell_reprices=2,
    )
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()  # SELL_WORKING at 1.95

    clock.advance(11)
    bot.tick()  # reprice #1
    clock.advance(11)
    bot.tick()  # reprice #2 -- count now at max

    clock.advance(11)
    # simulate the forced order filling at the bid once modify_order_price is called
    original_modify = broker.modify_order_price

    def modify_and_fill(order_id, qty, price):
        original_modify(order_id, qty, price)
        broker.fill(order_id, dealt_qty=qty, price=price)

    broker.modify_order_price = modify_and_fill
    bot.tick()  # forces exit at bid=1.00

    assert bot.state == State.IDLE
    assert len(round_trips) == 1
    rt = round_trips[0]
    assert rt.forced_exit is True
    assert rt.sell_price == pytest.approx(1.00)


def test_sell_reprice_never_goes_below_bid():
    broker = FakeBroker(bid=1.90, ask=2.00)
    clock = FakeClock()
    bot, _, _ = make_bot(
        broker, clock, min_spread_to_enter=0.05,
        sell_reprice_after_seconds=10, sell_reprice_step_ticks=100,
    )
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.95)
    bot.tick()  # SELL_WORKING at ask(2.00) - 1*0.05 = 1.95
    clock.advance(11)
    bot.tick()  # huge reprice step should clamp at bid, not go negative/below bid
    sell_order = broker.get_order(bot._sell_order_id)
    assert sell_order.price == pytest.approx(1.90)


def test_order_events_logged_for_buy_and_sell_submit():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, order_events = make_bot(broker, clock)
    bot.tick()  # submits buy
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()  # fills buy, submits sell

    assert [e.action for e in order_events] == ["SUBMIT", "SUBMIT"]
    buy_evt, sell_evt = order_events
    assert buy_evt.side == "BUY" and buy_evt.price == pytest.approx(1.05) and buy_evt.qty == 1
    assert sell_evt.side == "SELL" and sell_evt.price == pytest.approx(1.95) and sell_evt.qty == 1
    # both legs of the same round trip share a trip_seq
    assert buy_evt.trip_seq == sell_evt.trip_seq == 1


def test_order_events_trip_seq_increments_across_round_trips():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, order_events = make_bot(broker, clock)
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()
    broker.fill(bot._sell_order_id, dealt_qty=1, price=1.95)
    bot.tick()  # closes trip 1, back to IDLE

    bot.tick()  # submits buy for trip 2

    trip_seqs = [e.trip_seq for e in order_events]
    assert trip_seqs == [1, 1, 2]


def test_order_event_logged_on_buy_cancel_with_zero_fill():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, order_events = make_bot(broker, clock, buy_timeout_seconds=10)
    bot.tick()
    clock.advance(11)
    bot.tick()

    cancel_events = [e for e in order_events if e.action == "CANCEL"]
    assert len(cancel_events) == 1
    assert cancel_events[0].side == "BUY"


def test_order_event_logged_on_sell_reprice_and_force_exit():
    broker = FakeBroker(bid=1.00, ask=2.00)
    clock = FakeClock()
    bot, _, order_events = make_bot(
        broker, clock, sell_reprice_after_seconds=10, max_sell_reprices=1,
    )
    bot.tick()
    broker.fill(bot._buy_order_id, dealt_qty=1, price=1.05)
    bot.tick()  # SELL_WORKING at 1.95

    clock.advance(11)
    bot.tick()  # reprice #1 (now at max)

    clock.advance(11)
    original_modify = broker.modify_order_price

    def modify_and_fill(order_id, qty, price):
        original_modify(order_id, qty, price)
        broker.fill(order_id, dealt_qty=qty, price=price)

    broker.modify_order_price = modify_and_fill
    bot.tick()  # forces exit at bid

    actions = [e.action for e in order_events]
    assert actions == ["SUBMIT", "SUBMIT", "REPRICE", "FORCE_EXIT"]
    assert order_events[-1].price == pytest.approx(1.00)
