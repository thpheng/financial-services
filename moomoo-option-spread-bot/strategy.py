"""Spread-capture state machine.

Buy first, wait for the fill, THEN sell -- never rests both legs at once
(avoids self-match/wash-trade risk and the "bought and sold at the same
price for zero edge" failure mode of quoting both sides simultaneously).

Depends only on the small BrokerClient interface in moomoo_client.py, so it
can run against a fake in-memory broker in tests -- no OpenD needed to
verify the state transitions are correct.
"""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from moomoo_client import BrokerClient, OrderStatus


class State(Enum):
    IDLE = "IDLE"
    BUY_WORKING = "BUY_WORKING"
    SELL_WORKING = "SELL_WORKING"


TERMINAL_FILLED = {OrderStatus.FILLED_ALL}
TERMINAL_DEAD = {
    OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DISABLED,
    OrderStatus.DELETED, OrderStatus.SUBMIT_FAILED, OrderStatus.TIMEOUT,
}


@dataclass
class RoundTrip:
    """Record of one completed (or aborted) buy->sell cycle, for the audit log."""
    qty: float
    buy_price: float
    sell_price: Optional[float] = None
    forced_exit: bool = False
    aborted: bool = False
    note: str = ""


@dataclass
class SpreadCaptureBot:
    client: BrokerClient
    code: str
    qty: int
    step_size: float
    num_steps: int
    min_spread_to_enter: float
    buy_timeout_seconds: float
    sell_reprice_after_seconds: float
    sell_reprice_step_ticks: int
    max_sell_reprices: int
    on_round_trip: Callable[[RoundTrip], None] = lambda rt: None
    now_fn: Callable[[], float] = time.time

    state: State = field(default=State.IDLE, init=False)
    _buy_order_id: Optional[str] = field(default=None, init=False)
    _buy_placed_at: float = field(default=0.0, init=False)
    _buy_fill_price: float = field(default=0.0, init=False)
    _buy_fill_qty: float = field(default=0.0, init=False)
    _sell_order_id: Optional[str] = field(default=None, init=False)
    _sell_placed_at: float = field(default=0.0, init=False)
    _sell_reprice_count: int = field(default=0, init=False)

    def tick(self) -> None:
        if self.state == State.IDLE:
            self._try_enter()
        elif self.state == State.BUY_WORKING:
            self._watch_buy()
        elif self.state == State.SELL_WORKING:
            self._watch_sell()

    # -- IDLE: look for an entry --------------------------------------------
    def _try_enter(self) -> None:
        bid, ask = self.client.get_bid_ask(self.code)
        spread = ask - bid
        if spread < self.min_spread_to_enter:
            return
        buy_price = round(bid + self.num_steps * self.step_size, 2)
        if buy_price >= ask:
            return  # improved price would cross the offer -- no edge left
        order_id = self.client.place_limit_order(self.code, "BUY", self.qty, buy_price)
        self._buy_order_id = order_id
        self._buy_placed_at = self.now_fn()
        self.state = State.BUY_WORKING

    # -- BUY_WORKING: wait for the buy to fill --------------------------------
    def _watch_buy(self) -> None:
        order = self.client.get_order(self._buy_order_id)
        if order.status in TERMINAL_FILLED:
            self._buy_fill_price = order.price
            self._buy_fill_qty = order.dealt_qty
            self._place_sell(self._buy_fill_qty)
            return
        if order.status in TERMINAL_DEAD:
            self.state = State.IDLE
            self._buy_order_id = None
            return
        elapsed = self.now_fn() - self._buy_placed_at
        if elapsed >= self.buy_timeout_seconds:
            if order.dealt_qty > 0:
                # partially filled: stop trying to fill the rest, hedge what we have
                self.client.cancel_order(self._buy_order_id)
                self._buy_fill_price = order.price
                self._buy_fill_qty = order.dealt_qty
                self._place_sell(self._buy_fill_qty)
            else:
                self.client.cancel_order(self._buy_order_id)
                self.state = State.IDLE
                self._buy_order_id = None

    # -- transition into SELL_WORKING -----------------------------------------
    def _place_sell(self, qty: float) -> None:
        _, ask = self.client.get_bid_ask(self.code)
        sell_price = round(ask - self.num_steps * self.step_size, 2)
        if sell_price <= self._buy_fill_price:
            # market moved against us already -- still place the sell (we must
            # exit the position eventually), but note zero/negative edge upfront
            sell_price = max(sell_price, self._buy_fill_price)
        order_id = self.client.place_limit_order(self.code, "SELL", qty, sell_price)
        self._sell_order_id = order_id
        self._sell_placed_at = self.now_fn()
        self._sell_reprice_count = 0
        self.state = State.SELL_WORKING

    # -- SELL_WORKING: wait for the sell to fill, reprice/force-exit as needed
    def _watch_sell(self) -> None:
        order = self.client.get_order(self._sell_order_id)
        if order.status in TERMINAL_FILLED:
            self.on_round_trip(RoundTrip(
                qty=self._buy_fill_qty, buy_price=self._buy_fill_price, sell_price=order.price,
            ))
            self._reset_to_idle()
            return
        if order.status in TERMINAL_DEAD:
            # sell order died without filling (e.g. cancelled externally) --
            # we still hold the position, re-place a fresh sell immediately
            self._place_sell(self._buy_fill_qty)
            return

        elapsed = self.now_fn() - self._sell_placed_at
        if elapsed < self.sell_reprice_after_seconds:
            return

        if self._sell_reprice_count >= self.max_sell_reprices:
            # give up chasing -- cross the spread to force an exit rather than
            # sit on open-ended directional exposure
            bid, _ = self.client.get_bid_ask(self.code)
            self.client.modify_order_price(self._sell_order_id, self._buy_fill_qty, bid)
            self._sell_placed_at = self.now_fn()
            forced = self.client.get_order(self._sell_order_id)
            if forced.status in TERMINAL_FILLED:
                self.on_round_trip(RoundTrip(
                    qty=self._buy_fill_qty, buy_price=self._buy_fill_price,
                    sell_price=forced.price, forced_exit=True,
                ))
                self._reset_to_idle()
            return

        # reprice one step closer to the bid to improve fill odds
        current_price = order.price
        new_price = round(current_price - self.sell_reprice_step_ticks * self.step_size, 2)
        bid, _ = self.client.get_bid_ask(self.code)
        new_price = max(new_price, bid)
        self.client.modify_order_price(self._sell_order_id, self._buy_fill_qty, new_price)
        self._sell_placed_at = self.now_fn()
        self._sell_reprice_count += 1

    def _reset_to_idle(self) -> None:
        self.state = State.IDLE
        self._buy_order_id = None
        self._sell_order_id = None
        self._buy_fill_price = 0.0
        self._buy_fill_qty = 0.0
        self._sell_reprice_count = 0
