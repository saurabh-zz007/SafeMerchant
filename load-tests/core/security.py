"""
HMAC-SHA256 signature generator for Razorpay webhook payloads.
Matches Razorpay webhook security specifications.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Union


def generate_razorpay_signature(payload: Union[bytes, str, dict], secret: str) -> str:
    """
    Generate the HMAC-SHA256 hex signature for a webhook payload.

    :param payload: Webhook payload (bytes, raw JSON string, or dict)
    :param secret: Webhook secret string
    :return: Hexadecimal HMAC-SHA256 signature string
    """
    if isinstance(payload, dict):
        raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        raw_bytes = payload
    else:
        raise TypeError(f"Unsupported payload type: {type(payload)}")

    return hmac.new(
        secret.encode("utf-8"),
        raw_bytes,
        hashlib.sha256,
    ).hexdigest()
