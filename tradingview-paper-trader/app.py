import logging

from flask import Flask, jsonify, render_template, request

import config
import store
from alert_parser import AlertError, parse_alert
from moomoo_client import MoomooPaperTrader

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tv-paper-trader")

app = Flask(__name__)
store.init_db(config.DB_PATH)
trader = MoomooPaperTrader(config.OPEND_HOST, config.OPEND_PORT, config.ACC_INDEX)


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/webhook/tradingview", methods=["POST"])
def tradingview_webhook():
    raw_body = request.get_data()
    payload = request.get_json(silent=True) or {}

    phash = store.payload_hash(raw_body)
    if store.is_duplicate(config.DB_PATH, phash):
        log.info("duplicate webhook ignored (hash=%s)", phash[:8])
        return jsonify({"status": "duplicate_ignored"}), 200

    try:
        order = parse_alert(
            payload,
            expected_secret=config.WEBHOOK_SECRET,
            default_qty=config.DEFAULT_QTY,
            max_qty=config.MAX_QTY,
        )
    except AlertError as e:
        store.log_event(config.DB_PATH, raw_body=raw_body, status="rejected", error=str(e))
        log.warning("rejected webhook: %s", e)
        return jsonify({"status": "rejected", "error": str(e)}), 400

    try:
        result = trader.place_order(
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            order_type=order.order_type,
            price=order.price,
        )
    except Exception as e:  # OpenD unreachable, connection error, etc.
        store.log_event(
            config.DB_PATH, raw_body=raw_body, symbol=order.symbol, side=order.side,
            qty=order.qty, order_type=order.order_type, price=order.price,
            status="error", error=str(e),
        )
        log.exception("failed to reach moomoo OpenD")
        return jsonify({"status": "error", "error": str(e)}), 502

    if not result.ok:
        store.log_event(
            config.DB_PATH, raw_body=raw_body, symbol=order.symbol, side=order.side,
            qty=order.qty, order_type=order.order_type, price=order.price,
            status="rejected_by_broker", error=result.error,
        )
        return jsonify({"status": "rejected_by_broker", "error": result.error}), 502

    store.log_event(
        config.DB_PATH, raw_body=raw_body, symbol=order.symbol, side=order.side,
        qty=order.qty, order_type=order.order_type, price=order.price,
        status="submitted", order_id=result.order_id, order_status=result.order_status,
    )
    log.info("submitted paper order %s %s x%s (order_id=%s)", order.side, order.symbol, order.qty, result.order_id)
    return jsonify({
        "status": "submitted",
        "order_id": result.order_id,
        "order_status": result.order_status,
    }), 200


@app.route("/api/log")
def api_log():
    return jsonify(store.recent_events(config.DB_PATH, limit=100))


@app.route("/api/positions")
def api_positions():
    try:
        return jsonify(trader.get_positions())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/orders")
def api_orders():
    try:
        return jsonify(trader.get_orders())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/account")
def api_account():
    try:
        return jsonify(trader.get_account_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    if not config.WEBHOOK_SECRET:
        log.warning("WEBHOOK_SECRET is not set — every webhook will be rejected until it is.")
    app.run(host=config.APP_HOST, port=config.APP_PORT)
