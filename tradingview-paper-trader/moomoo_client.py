"""Thin wrapper around the moomoo/Futu OpenD trade API.

Hardcoded to TrdEnv.SIMULATE (paper trading) everywhere — trd_env is never
taken from caller input, so this client cannot place a live order even if a
webhook payload were tampered with.
"""
from dataclasses import dataclass
from typing import Optional

from futu import OpenSecTradeContext, TrdEnv, RET_OK


@dataclass
class OrderResult:
    ok: bool
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    error: Optional[str] = None


class MoomooPaperTrader:
    def __init__(self, host: str, port: int, acc_index: int = 0):
        self._host = host
        self._port = port
        self._acc_index = acc_index

    def _context(self) -> OpenSecTradeContext:
        return OpenSecTradeContext(host=self._host, port=self._port)

    def place_order(self, symbol: str, side: str, qty: int, order_type: str, price: float) -> OrderResult:
        code = f"US.{symbol}"
        with self._context() as trd_ctx:
            ret, data = trd_ctx.place_order(
                price=price,
                qty=qty,
                code=code,
                trd_side=side,
                order_type=order_type,
                trd_env=TrdEnv.SIMULATE,
                acc_index=self._acc_index,
            )
            if ret != RET_OK:
                return OrderResult(ok=False, error=str(data))
            row = data.iloc[0]
            return OrderResult(
                ok=True,
                order_id=str(row.get("order_id")),
                order_status=str(row.get("order_status")),
            )

    def get_positions(self) -> list:
        with self._context() as trd_ctx:
            ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.SIMULATE, acc_index=self._acc_index)
            if ret != RET_OK:
                raise RuntimeError(str(data))
            return data.to_dict("records")

    def get_orders(self) -> list:
        with self._context() as trd_ctx:
            ret, data = trd_ctx.order_list_query(trd_env=TrdEnv.SIMULATE, acc_index=self._acc_index)
            if ret != RET_OK:
                raise RuntimeError(str(data))
            return data.to_dict("records")

    def get_account_info(self) -> dict:
        with self._context() as trd_ctx:
            ret, data = trd_ctx.accinfo_query(
                trd_env=TrdEnv.SIMULATE, acc_index=self._acc_index, currency="USD"
            )
            if ret != RET_OK:
                raise RuntimeError(str(data))
            records = data.to_dict("records")
            return records[0] if records else {}
