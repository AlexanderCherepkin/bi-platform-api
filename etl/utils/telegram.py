"""Sync Telegram notifications for ETL failures and anomalies."""

import json
import logging
import os
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram_message(text: str) -> bool:
    """Send a plain-text message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram not configured; message dropped: %s", text[:200])
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        logger.info("Telegram message sent")
        return True
    except URLError as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False
    except Exception as exc:
        logger.warning("Telegram send failed unexpectedly: %s", exc)
        return False
