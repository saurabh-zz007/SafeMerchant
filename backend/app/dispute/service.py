"""
Dispute orchestration service.

Bridges the FastAPI webhook handler and the LangGraph agent.
Converts webhook payloads into initial agent state and invokes the graph.

Refactored for HITL: the compiled graph is injected (not a module-level
singleton), and streaming accepts a ``config`` with ``thread_id`` for
checkpoint persistence.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional

from app.dispute.agent.state import DisputeAgentState
from app.dispute.schemas.webhook import DisputeWebhookEvent

logger = logging.getLogger(__name__)


class DisputeService:
    """
    Stateless service that processes dispute webhooks through the LangGraph.
    """

    @staticmethod
    def webhook_to_initial_state(event: DisputeWebhookEvent) -> DisputeAgentState:
        """Convert a validated webhook event into the initial LangGraph state."""
        # FIXED: Extract data from the correctly nested payload
        dispute_data = event.payload.dispute.entity
        payment_data = event.payload.payment.entity

        return DisputeAgentState(
            # Stage 0 — Ingestion
            dispute_id=dispute_data.id,
            payment_id=payment_data.id,
            order_id=payment_data.order_id, 
            reason_code=dispute_data.reason_code,
            disputed_amount_inr=dispute_data.amount,
            amount_deducted=dispute_data.amount_deducted,
            respond_by=dispute_data.respond_by,
            dispute_phase=dispute_data.phase,
            customer_email=payment_data.email, 
            dispute_created_at=dispute_data.created_at,

            # Stage 1 — Evidence
            evidence_bundle=None,
            evidence_collected_at=None,
            evidence_summary=None,

            # Stage 2 — Triage
            winnability_score=None,
            risk_factors=[],
            triage_reasoning=None,
            recommended_action=None,
            customer_legitimacy_signal=False,
            legitimacy_reasoning=None,

            # Stage 3 — Draft (Steps A, B, C)
            comms_extraction=None,
            draft_summary=None,
            draft_explanation_letter=None,
            draft_evidence_fields=None,
            verification_report=None,
            verified_explanation_letter=None,
            verified_evidence_fields=None,
            draft_response_letter=None,
            cited_evidence_keys=[],

            # Gate
            gate_action=None,
            requires_human_review=False,
            human_review_reason=None,
            refund_id=None,
            refund_status=None,
            case_resolution=None,

            # HITL
            user_decision=None,

            # Observability
            current_node="ingestion",
            node_history=["ingestion"],
            messages=[],
            error=None,
        )

    async def stream_dispute(
        self,
        event: DisputeWebhookEvent,
        compiled_graph,
        config: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream the dispute pipeline node-by-node for WebSocket observability.
        Yields partial state updates as each node completes.

        Args:
            event: The validated webhook event (used for first run only).
            compiled_graph: The LangGraph compiled with checkpointer.
            config: Must contain ``{"configurable": {"thread_id": dispute_id}}``.
        """
        initial_state = self.webhook_to_initial_state(event)
        logger.info(
            "Streaming dispute %s for payment %s (thread_id=%s)",
            initial_state["dispute_id"],
            initial_state["payment_id"],
            config.get("configurable", {}).get("thread_id", "?"),
        )

        async for event_data in compiled_graph.astream(initial_state, config):
            # Each event_data is {node_name: partial_state_update}
            for node_name, state_update in event_data.items():
                yield {
                    "node": node_name,
                    "state_update": state_update,
                }

    async def stream_resume(
        self,
        compiled_graph,
        config: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Resume a paused graph after HITL review.

        Streams from the interrupt point forward. The graph state should
        already have been updated with the user's decision via
        ``graph.aupdate_state()`` before calling this.

        Args:
            compiled_graph: The LangGraph compiled with checkpointer.
            config: Must contain ``{"configurable": {"thread_id": dispute_id}}``.
        """
        logger.info(
            "Resuming dispute graph (thread_id=%s)",
            config.get("configurable", {}).get("thread_id", "?"),
        )

        async for event_data in compiled_graph.astream(None, config):
            for node_name, state_update in event_data.items():
                yield {
                    "node": node_name,
                    "state_update": state_update,
                }


# Singleton instance
dispute_service = DisputeService()
