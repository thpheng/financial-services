"""One-off helper: look up the exact moomoo contract code for an option so you
don't have to hand-build the OCC-style string yourself.

Usage:
    python3 find_option_code.py US.AMD 2026-01-16
"""
import sys

from futu import OpenQuoteContext, RET_OK

import config


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python3 find_option_code.py <underlying code> <expiry YYYY-MM-DD>")
        print("Example: python3 find_option_code.py US.AMD 2026-01-16")
        return 1

    underlying, expiry = sys.argv[1], sys.argv[2]
    quote_ctx = OpenQuoteContext(host=config.OPEND_HOST, port=config.OPEND_PORT)
    try:
        ret, data = quote_ctx.get_option_chain(code=underlying, start=expiry, end=expiry)
        if ret != RET_OK:
            print(f"error: {data}")
            return 1
        if len(data) == 0:
            print(f"no option chain found for {underlying} expiring {expiry}")
            return 1
        print(data[["code", "name", "option_type", "strike_price", "strike_time"]].to_string(index=False))
        return 0
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    sys.exit(main())
