"""
Razorpay Refunds API client — thin async wrapper.

Used by the auto_refund terminal node to execute refunds via
POST /v1/payments/{payment_id}/refund.

DEFENSE-ONLY: This is the only mutation the system performs,
and only when the gate determines the customer is legitimately owed a refund.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


async def execute_razorpay_refund(
    payment_id: str,
    amount: int,
    reason: str = "Dispute resolved — customer refund",
) -> dict:
    """
    Execute a refund via the Razorpay Payments API.

    POST /v1/payments/{payment_id}/refund

    Args:
        payment_id: Razorpay payment ID (e.g., "pay_XYZ1001")
        amount: Refund amount in paisa
        reason: Human-readable reason for the refund

    Returns:
        dict with keys: refund_id, status, error (if any)
    """
    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret

    if not key_id or not key_secret:
        logger.warning(
            "Razorpay credentials not configured — skipping refund for %s",
            payment_id,
        )
        return {
            "refund_id": None,
            "status": "failed",
            "error": "Razorpay API credentials not configured",
        }

    url = f"{RAZORPAY_API_BASE}/payments/{payment_id}/refund"
    payload = {
        "amount": amount,
        "notes": {
            "reason": reason,
            "source": "safemerchant_agent",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(key_id, key_secret),
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                refund_id = data.get("id", "unknown")
                status = data.get("status", "unknown")
                logger.info(
                    "Refund executed: %s → status=%s for payment %s",
                    refund_id, status, payment_id,
                )
                return {
                    "refund_id": refund_id,
                    "status": status,
                    "error": None,
                }
            else:
                error_msg = response.text
                logger.error(
                    "Razorpay refund failed for %s: HTTP %d — %s",
                    payment_id, response.status_code, error_msg,
                )
                return {
                    "refund_id": None,
                    "status": "failed",
                    "error": f"HTTP {response.status_code}: {error_msg}",
                }

    except httpx.TimeoutException:
        logger.error("Razorpay refund timeout for %s", payment_id)
        return {
            "refund_id": None,
            "status": "failed",
            "error": "Request timeout",
        }
    except Exception as e:
        logger.exception("Unexpected error during Razorpay refund for %s", payment_id)
        return {
            "refund_id": None,
            "status": "failed",
            "error": str(e),
        }
