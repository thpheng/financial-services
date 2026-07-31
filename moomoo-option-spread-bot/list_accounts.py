"""Diagnostic: list every trading account visible to this login, with the
fields that matter for picking the right one -- trd_env (SIMULATE/REAL),
sim_acc_type, and trdmarket_auth (which markets/products it's actually
authorized to trade, as opposed to just view data for).

Run this whenever an order gets rejected with "Account does not support
trading X" -- acc_index=0 (the default) just grabs whichever account comes
first, which is not necessarily the one approved for options.
"""
import sys

import pandas as pd
from futu import OpenSecTradeContext, RET_OK, TrdMarket

import config


def main() -> int:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)

    # OpenSecTradeContext defaults to filter_trdmarket='HK', which silently
    # hides any account (like a US-only paper trading account) that doesn't
    # include HK in its own market list. This bot only ever trades US
    # options, so filter on US explicitly instead of the HK default.
    trd_ctx = OpenSecTradeContext(
        host=config.OPEND_HOST, port=config.OPEND_PORT, filter_trdmarket=TrdMarket.US,
    )
    try:
        ret, data = trd_ctx.get_acc_list()
        if ret != RET_OK:
            print(f"error: {data}")
            return 1
        print(data[["acc_id", "trd_env", "acc_type", "sim_acc_type", "trdmarket_auth", "acc_status"]]
              .to_string(index=False))
        print()
        print("Look for a row with trd_env=SIMULATE whose trdmarket_auth includes 'US' "
              "and/or sim_acc_type suggests options. Put that row's acc_id in ACC_ID in .env.")
        return 0
    finally:
        trd_ctx.close()


if __name__ == "__main__":
    sys.exit(main())
