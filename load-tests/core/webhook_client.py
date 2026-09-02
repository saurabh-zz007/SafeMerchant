"""
Custom signed webhook client helper for Locust load testing.
Encapsulates signing and posting payloads to the webhook endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from config.settings import settings
from core.security import generate_razorpay_signature

logger = logging.getLogger(__name__)


class SignedWebhookClient:
    """Helper client for sending HMAC-signed webhook requests."""

    @staticmethod
    def post_dispute_webhook(
        client: Any,
        payload: dict,
        name: Optional[str] = None,
        path: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> Any:
        """
        Signs the JSON payload and dispatches a POST request through Locust's client.

        :param client: Locust HttpSession or requests client
        :param payload: Webhook JSON dictionary
        :param name: Label for Locust stats grouping
        :param path: Webhook endpoint URL path
        :param secret: Razorpay webhook secret
        :return: Response object from Locust client
        """
        webhook_path = path or settings.WEBHOOK_PATH
        webhook_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET

        raw_json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = generate_razorpay_signature(raw_json_bytes, webhook_secret)

        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        }

        request_name = name or f"Webhook: {payload.get('payload', {}).get('dispute', {}).get('entity', {}).get('reason_code', 'unknown')}"

        with client.post(
            webhook_path,
            data=raw_json_bytes,
            headers=headers,
            name=request_name,
            catch_response=True,
            timeout=settings.REQUEST_TIMEOUT,
        ) as response:
            if response.status_code in (200, 202):
                response.success()
            else:
                response.failure(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
            return response
