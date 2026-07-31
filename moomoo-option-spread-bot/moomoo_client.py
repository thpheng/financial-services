"""Thin wrapper around the moomoo/Futu OpenD quote + trade APIs.

Only this module imports `futu` and only this module knows about OpenD --
`strategy.py` talks to a small interface (see BrokerClient protocol below)
so the state machine can be unit tested without a live OpenD connection.
"""
from dataclasses import dataclass
from typing import Optional, Protocol

from futu import (
    ModifyOrderOp,
    OpenQuoteContext,
    OpenSecTradeContext,
    OrderStatus,
    RET_OK,
    SubType,
    TrdEnv,
    TrdSide,
)


@dataclass
class Order:
    order_id: str
    status: str  # one of futu.OrderStatus values
    dealt_qty: float
    price: float


class BrokerClient(Protocol):
    """Interface strategy.py programs against -- see FakeBrokerClient in tests
    for the in-memory implementation used by the unit tests."""

    def get_bid_ask(self, code: str) -> tuple[float, float]: ...
    def place_limit_order(self, code: str, side: str, qty: float, price: float) -> str: ...
    def get_order(self, order_id: str) -> Order: ...
    def modify_order_price(self, order_id: str, qty: float, price: float) -> None: ...
    def cancel_order(self, order_id: str) -> None: ...


class MoomooBrokerClient:
    """Real BrokerClient backed by a moomoo OpenD connection."""

    def __init__(self, host: str, port: int, trading_mode: str, acc_index: int = 0,
                 acc_id: int = 0, unlock_password: str = ""):
        self.trd_env = TrdEnv.SIMULATE if trading_mode.upper() == "SIMULATE" else TrdEnv.REAL
        self._acc_index = acc_index
        self._acc_id = acc_id
        self.quote_ctx = OpenQuoteContext(host=host, port=port)
        self.trd_ctx = OpenSecTradeContext(host=host, port=port)
        if self.trd_env == TrdEnv.REAL:
            if not unlock_password:
                raise RuntimeError(
                    "TRADING_MODE=REAL requires TRADE_UNLOCK_PASSWORD to be set -- "
                    "refusing to start unlocked-by-accident."
                )
            ret, msg = self.trd_ctx.unlock_trade(password=unlock_password)
            if ret != RET_OK:
                raise RuntimeError(f"failed to unlock real trading: {msg}")

    def subscribe(self, code: str) -> None:
        ret, msg = self.quote_ctx.subscribe([code], [SubType.ORDER_BOOK])
        if ret != RET_OK:
            raise RuntimeError(f"failed to subscribe to {code}: {msg}")

    def get_bid_ask(self, code: str) -> tuple[float, float]:
        ret, book = self.quote_ctx.get_order_book(code)
        if ret != RET_OK:
            raise RuntimeError(f"get_order_book failed: {book}")
        bid = book["Bid"][0][0] if book.get("Bid") else None
        ask = book["Ask"][0][0] if book.get("Ask") else None
        if bid is None or ask is None:
            raise RuntimeError(f"no two-sided quote available for {code}")
        return float(bid), float(ask)

    def place_limit_order(self, code: str, side: str, qty: float, price: float) -> str:
        trd_side = TrdSide.BUY if side == "BUY" else TrdSide.SELL
        ret, data = self.trd_ctx.place_order(
            price=price, qty=qty, code=code, trd_side=trd_side,
            order_type="NORMAL", trd_env=self.trd_env,
            acc_id=self._acc_id, acc_index=self._acc_index,
        )
        if ret != RET_OK:
            raise RuntimeError(f"place_order failed: {data}")
        return str(data.iloc[0]["order_id"])

    def get_order(self, order_id: str) -> Order:
        ret, data = self.trd_ctx.order_list_query(
            order_id=order_id, trd_env=self.trd_env,
            acc_id=self._acc_id, acc_index=self._acc_index, refresh_cache=True,
        )
        if ret != RET_OK:
            raise RuntimeError(f"order_list_query failed: {data}")
        if len(data) == 0:
            raise RuntimeError(f"order {order_id} not found")
        row = data.iloc[0]
        return Order(
            order_id=str(row["order_id"]),
            status=str(row["order_status"]),
            dealt_qty=float(row["dealt_qty"]),
            price=float(row["price"]),
        )

    def modify_order_price(self, order_id: str, qty: float, price: float) -> None:
        ret, msg = self.trd_ctx.modify_order(
            ModifyOrderOp.NORMAL, order_id, qty, price, trd_env=self.trd_env,
            acc_id=self._acc_id, acc_index=self._acc_index,
        )
        if ret != RET_OK:
            raise RuntimeError(f"modify_order failed: {msg}")

    def cancel_order(self, order_id: str) -> None:
        order = self.get_order(order_id)
        ret, msg = self.trd_ctx.modify_order(
            ModifyOrderOp.CANCEL, order_id, order.dealt_qty, order.price,
            trd_env=self.trd_env, acc_id=self._acc_id, acc_index=self._acc_index,
        )
        if ret != RET_OK:
            raise RuntimeError(f"cancel_order failed: {msg}")

    def close(self) -> None:
        self.quote_ctx.close()
        self.trd_ctx.close()


TERMINAL_FILLED = {OrderStatus.FILLED_ALL}
TERMINAL_DEAD = {
    OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DISABLED,
    OrderStatus.DELETED, OrderStatus.SUBMIT_FAILED, OrderStatus.TIMEOUT,
}
