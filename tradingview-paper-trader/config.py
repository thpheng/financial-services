import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


OPEND_HOST = os.environ.get("OPEND_HOST", "127.0.0.1")
OPEND_PORT = _int("OPEND_PORT", 11111)
ACC_INDEX = _int("ACC_INDEX", 0)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

DEFAULT_QTY = _int("DEFAULT_QTY", 1)
MAX_QTY = _int("MAX_QTY", 10_000)

DB_PATH = os.environ.get("DB_PATH", "trades.db")

APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = _int("APP_PORT", 5000)
