import logging
import os

LOG_FILE = os.getenv("LOG_FILE", "trades.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("rde")


def log_trade(email: str, broker: str, signal: str, stake: float, result: str):
    logger.info(f"TRADE | user={email} broker={broker} signal={signal} stake={stake} result={result}")


def log_error(email: str, message: str):
    logger.error(f"ERROR | user={email} {message}")


def log_admin(admin_email: str, action: str, target: str):
    logger.info(f"ADMIN | by={admin_email} action={action} target={target}")
