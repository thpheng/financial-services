import logging
import signal
import sys
import time

import config
import store
from moomoo_client import MoomooBrokerClient
from strategy import RoundTrip, SpreadCaptureBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("spread-bot")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("shutdown requested, finishing current tick then stopping...")
    _shutdown = True


def main() -> int:
    if not config.OPTION_CODE:
        log.error("OPTION_CODE is not set in .env -- nothing to trade.")
        return 1

    log.info("mode=%s code=%s qty=%s step=%.2f x%s min_spread=%.2f",
              config.TRADING_MODE, config.OPTION_CODE, config.QTY, config.STEP_SIZE,
              config.NUM_STEPS, config.MIN_SPREAD_TO_ENTER)

    if config.TRADING_MODE == "REAL":
        log.warning("TRADING_MODE=REAL -- this will submit REAL orders with REAL money.")

    store.init_db(config.DB_PATH)

    client = MoomooBrokerClient(
        host=config.OPEND_HOST, port=config.OPEND_PORT, trading_mode=config.TRADING_MODE,
        acc_index=config.ACC_INDEX, acc_id=config.ACC_ID,
        unlock_password=config.TRADE_UNLOCK_PASSWORD,
    )
    client.subscribe(config.OPTION_CODE)

    def on_round_trip(rt: RoundTrip) -> None:
        rt.code = config.OPTION_CODE
        store.log_round_trip(config.DB_PATH, rt)
        edge = (rt.sell_price - rt.buy_price) * rt.qty * 100 if rt.sell_price else None
        log.info(
            "ROUND TRIP closed: qty=%s buy=%.2f sell=%s edge=$%s forced_exit=%s",
            rt.qty, rt.buy_price,
            f"{rt.sell_price:.2f}" if rt.sell_price is not None else "None",
            f"{edge:.2f}" if edge is not None else "None",
            rt.forced_exit,
        )

    bot = SpreadCaptureBot(
        client=client,
        code=config.OPTION_CODE,
        qty=config.QTY,
        step_size=config.STEP_SIZE,
        num_steps=config.NUM_STEPS,
        min_spread_to_enter=config.MIN_SPREAD_TO_ENTER,
        buy_timeout_seconds=config.BUY_TIMEOUT_SECONDS,
        sell_reprice_after_seconds=config.SELL_REPRICE_AFTER_SECONDS,
        sell_reprice_step_ticks=config.SELL_REPRICE_STEP_TICKS,
        max_sell_reprices=config.MAX_SELL_REPRICES,
        on_round_trip=on_round_trip,
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    consecutive_errors = 0
    try:
        while not _shutdown:
            try:
                bot.tick()
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                log.exception(
                    "error during tick (%d/%d consecutive) -- will retry next poll",
                    consecutive_errors, config.MAX_CONSECUTIVE_ERRORS,
                )
                if consecutive_errors >= config.MAX_CONSECUTIVE_ERRORS:
                    log.error(
                        "%d consecutive errors -- stopping automatically instead of "
                        "retrying forever. Check the traceback above, fix the underlying "
                        "issue, then restart.", consecutive_errors,
                    )
                    break
            time.sleep(config.POLL_INTERVAL_SECONDS)
    finally:
        log.info("stopping -- canceling any open orders")
        for order_id in (bot._buy_order_id, bot._sell_order_id):
            if order_id:
                try:
                    client.cancel_order(order_id)
                    log.info("cancelled open order %s", order_id)
                except Exception:
                    log.exception("failed to cancel order %s -- check moomoo app manually", order_id)
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
