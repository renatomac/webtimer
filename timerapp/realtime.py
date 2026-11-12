"""Server-only Ably authentication and timer notifications."""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def timer_channel(user_id):
    return f"user-{user_id}-timer"


def create_token_request(user_id):
    key_name, secret = settings.ABLY_API_KEY.split(":", 1)
    if not key_name or not secret:
        raise ValueError("Invalid Ably configuration")
    data = {
        "keyName": key_name,
        "ttl": 3600000,
        "capability": json.dumps({timer_channel(user_id): ["subscribe"]}, separators=(",", ":")),
        "clientId": str(user_id),
        "timestamp": int(time.time() * 1000),
        "nonce": secrets.token_hex(16),
    }
    canonical = "".join(f"{data[field]}\n" for field in (
        "keyName", "ttl", "capability", "clientId", "timestamp", "nonce"
    ))
    data["mac"] = base64.b64encode(
        hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()
    ).decode()
    return data


def publish_timer_update(user_id, payload):
    if not settings.ABLY_API_KEY:
        return
    try:
        key_name, secret = settings.ABLY_API_KEY.split(":", 1)
        response = requests.post(
            f"https://rest.ably.io/channels/{quote(timer_channel(user_id), safe='')}/messages",
            auth=(key_name, secret),
            json={"name": "update", "data": payload},
            timeout=(2, 3),
        )
        response.raise_for_status()
    except (requests.RequestException, ValueError):
        # Do not log credentials or response bodies. Polling will reconcile state.
        logger.warning("Ably timer publish failed; displays will recover through polling")
