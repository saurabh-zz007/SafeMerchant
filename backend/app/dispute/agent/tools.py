"""
LangGraph tool: fetch_dispute_evidence

This is the ONLY tool available to the agent. It performs read-only queries
against the merchant database to gather evidence for chargeback defense.

DEFENSE-ONLY: This tool cannot modify, delete, or create any data.
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

from app.core.db import async_session_factory
from app.dispute.repository import EvidenceRepository


@tool
async def fetch_dispute_evidence(
    order_id: Optional[str] = None,
    payment_id: Optional[str] = None,
) -> str:
    """
    Fetches all internal merchant records (order details, shipping logs,
    support history, risk telemetry) tied to a specific order ID or payment ID.

    Args:
        order_id: The unique merchant order ID (e.g., ORD_1001)
        payment_id: The Razorpay payment ID (e.g., pay_XYZ1001)

    Returns:
        JSON string with the evidence bundle, or an error message.
    """
    if not order_id and not payment_id:
        return json.dumps({"error": "At least one of order_id or payment_id must be provided"})

    async with async_session_factory() as session:
        repo = EvidenceRepository(session)
        evidence = await repo.fetch_full_evidence(
            order_id=order_id,
            payment_id=payment_id,
        )

    if evidence is None:
        return json.dumps({
            "error": f"No order found for order_id={order_id}, payment_id={payment_id}"
        })

    return json.dumps(evidence, default=str)


# List of all tools available to the agent — defense-only, read-only
AGENT_TOOLS = [fetch_dispute_evidence]
