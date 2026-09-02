"""
Super Step 1 — Evidence Retrieval.

Query the merchant database for all evidence related to the disputed order.
Uses the EvidenceRepository for read-only database access.

Pipeline position: START → [retrieve_evidence] → triage_and_score → ...
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.db import async_session_factory
from app.dispute.agent.state import DisputeAgentState
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.repository import EvidenceRepository

logger = logging.getLogger(__name__)


async def retrieve_evidence(state: DisputeAgentState) -> dict[str, Any]:
    """
    Query the merchant database for all evidence related to the disputed order.
    Uses the fetch_dispute_evidence tool via the repository layer.
    """
    dispute_id = state.get("dispute_id")
    order_id = state.get("order_id")
    payment_id = state.get("payment_id")

    async with async_session_factory() as session:
        # Check idempotency: skip if already processed or document_id attached
        if dispute_id:
            dispute_repo = DisputeRepository(session)
            dispute = await dispute_repo.get_dispute(dispute_id)
            if dispute:
                phase = (dispute.phase or "").lower()
                if (phase in ("chargeback", "contested") and dispute.status in ("under_review", "resolved")) or dispute.document_id:
                    logger.info("Dispute already processed: %s", dispute_id)
                    return {
                        "evidence_bundle": None,
                        "evidence_collected_at": datetime.now(timezone.utc).isoformat(),
                        "current_node": "retrieve_evidence",
                        "node_history": state.get("node_history", []) + ["retrieve_evidence"],
                        "error": "Dispute already processed",
                    }

        repo = EvidenceRepository(session)
        evidence = await repo.fetch_full_evidence(
            order_id=order_id,
            payment_id=payment_id,
        )

    if evidence is None:
        return {
            "evidence_bundle": None,
            "evidence_collected_at": datetime.now(timezone.utc).isoformat(),
            "current_node": "retrieve_evidence",
            "node_history": state.get("node_history", []) + ["retrieve_evidence"],
            "error": f"No order found for order_id={order_id}, payment_id={payment_id}",
        }

    return {
        "evidence_bundle": evidence,
        "evidence_collected_at": datetime.now(timezone.utc).isoformat(),
        "current_node": "retrieve_evidence",
        "node_history": state.get("node_history", []) + ["retrieve_evidence"],
        "error": None,
    }
