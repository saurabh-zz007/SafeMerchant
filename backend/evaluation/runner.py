"""
Batch evaluation runner.

Runs the full dispute pipeline over synthetic disputes by monkeypatching
the EvidenceRepository to return synthetic evidence bundles instead of
hitting the real database.

Usage:
    from evaluation.runner import run_evaluation_batch
    results = await run_evaluation_batch(disputes)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.dispute.schemas.webhook import DisputeWebhookEvent
from app.dispute.service import DisputeService

logger = logging.getLogger(__name__)


async def _run_single_dispute(
    dispute: dict[str, Any],
    service: DisputeService,
) -> dict[str, Any]:
    """
    Run a single dispute through the pipeline with mocked evidence.

    We mock the entire retrieve_evidence node function to inject the synthetic
    evidence directly into the state, bypassing the DB entirely.
    """
    webhook_payload = dispute["webhook_payload"]
    evidence_bundle = dispute["evidence_bundle"]
    ground_truth = dispute["ground_truth"]
    ground_truth_category = dispute["ground_truth_category"]

    # Parse the webhook event
    event = DisputeWebhookEvent(**webhook_payload)
    dispute_id = event.payload.dispute.entity.id

    try:
        from datetime import datetime, timezone

        # Create a replacement retrieve_evidence that returns synthetic evidence
        async def mock_retrieve_evidence(state):
            return {
                "evidence_bundle": evidence_bundle,
                "evidence_collected_at": datetime.now(timezone.utc).isoformat(),
                "current_node": "retrieve_evidence",
                "node_history": state.get("node_history", []) + ["retrieve_evidence"],
                "error": None,
            }

        # Also mock the LLM-based draft to avoid real API calls
        # (super_step_3 calls get_llm which needs real OpenRouter credentials)
        async def mock_draft_response(state):
            """Template-based draft — no LLM calls needed for evaluation."""
            evidence = state.get("evidence_bundle")
            score = state.get("winnability_score", 0.0)
            recommended_action = state.get("recommended_action", "contest")
            dispute_id = state.get("dispute_id", "UNKNOWN")

            base_update = {
                "current_node": "draft_response",
                "node_history": state.get("node_history", []) + ["draft_response"],
            }

            if recommended_action in ("refund_customer", "accept_loss") or evidence is None:
                return {
                    **base_update,
                    "comms_extraction": None,
                    "draft_summary": f"Skipping draft — action: {recommended_action}",
                    "draft_explanation_letter": None,
                    "draft_evidence_fields": None,
                    "verification_report": None,
                    "verified_explanation_letter": None,
                    "verified_evidence_fields": None,
                    "draft_response_letter": None,
                    "cited_evidence_keys": [],
                }

            # Simple template draft for evaluation
            cited_keys = []
            if evidence.get("order"):
                cited_keys.append("order")
            if evidence.get("shipping"):
                cited_keys.append("shipping")
            if evidence.get("communications"):
                cited_keys.append("communications")
            if evidence.get("risk_signals"):
                cited_keys.append("risk_signals")

            return {
                **base_update,
                "comms_extraction": {
                    "acknowledged_receipt": False,
                    "complaint_before_dispute": False,
                    "relevant_quote_ref": "",
                },
                "draft_summary": f"Template draft for {dispute_id}",
                "draft_explanation_letter": f"Evidence-based response for dispute {dispute_id}",
                "draft_evidence_fields": None,
                "verification_report": None,
                "verified_explanation_letter": None,
                "verified_evidence_fields": None,
                "draft_response_letter": f"Evidence-based response for dispute {dispute_id}",
                "cited_evidence_keys": cited_keys,
            }

        # Patch both the evidence retrieval and draft response nodes
        with patch(
            "app.dispute.agent.nodes.super_step_1.retrieve_evidence",
            side_effect=mock_retrieve_evidence,
        ), patch(
            "app.dispute.agent.nodes.super_step_3.draft_response",
            side_effect=mock_draft_response,
        ):
            # Need to rebuild the graph with mocked nodes
            from app.dispute.agent.nodes.super_step_2 import triage_and_score
            from app.dispute.agent.nodes.gate import (
                gate_decision,
                auto_submit_node,
                human_review_node,
                accept_loss_node,
                auto_refund_node,
                refund_review_node,
            )
            from app.dispute.agent.state import DisputeAgentState
            from langgraph.graph import END, StateGraph

            graph = StateGraph(DisputeAgentState)
            graph.add_node("retrieve_evidence", mock_retrieve_evidence)
            graph.add_node("triage_and_score", triage_and_score)
            graph.add_node("draft_response", mock_draft_response)
            graph.add_node("auto_submit", auto_submit_node)
            graph.add_node("human_review", human_review_node)
            graph.add_node("accept_loss", accept_loss_node)
            graph.add_node("auto_refund", auto_refund_node)
            graph.add_node("refund_review", refund_review_node)

            graph.set_entry_point("retrieve_evidence")
            graph.add_edge("retrieve_evidence", "triage_and_score")
            graph.add_edge("triage_and_score", "draft_response")
            graph.add_conditional_edges(
                "draft_response",
                gate_decision,
                {
                    "auto_submit": "auto_submit",
                    "human_review": "human_review",
                    "accept_loss": "accept_loss",
                    "auto_refund": "auto_refund",
                    "refund_review": "refund_review",
                },
            )
            graph.add_edge("auto_submit", END)
            graph.add_edge("human_review", END)
            graph.add_edge("accept_loss", END)
            graph.add_edge("auto_refund", END)
            graph.add_edge("refund_review", END)

            compiled = graph.compile()

            initial_state = service.webhook_to_initial_state(event)
            final_state = await compiled.ainvoke(initial_state)

        predicted_action = final_state.get("gate_action", "unknown")
        winnability_score = final_state.get("winnability_score", 0.0)
        recommended_action = final_state.get("recommended_action", "unknown")
        legitimacy = final_state.get("customer_legitimacy_signal", False)
        case_resolution = final_state.get("case_resolution", "unknown")

        return {
            "dispute_id": dispute_id,
            "ground_truth": ground_truth,
            "ground_truth_category": ground_truth_category,
            "predicted_action": predicted_action,
            "winnability_score": winnability_score,
            "recommended_action": recommended_action,
            "customer_legitimacy": legitimacy,
            "case_resolution": case_resolution,
            "amount": event.payload.dispute.entity.amount,
            "correct": predicted_action == ground_truth,
            "error": final_state.get("error"),
        }
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", dispute_id, e)
        return {
            "dispute_id": dispute_id,
            "ground_truth": ground_truth,
            "ground_truth_category": ground_truth_category,
            "predicted_action": "error",
            "winnability_score": 0.0,
            "recommended_action": "error",
            "customer_legitimacy": False,
            "case_resolution": "error",
            "amount": webhook_payload.get("payload", {}).get("dispute", {}).get("entity", {}).get("amount", 0),
            "correct": False,
            "error": str(e),
        }


async def run_evaluation_batch(
    disputes: list[dict[str, Any]],
    *,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """
    Run the full pipeline over a batch of synthetic disputes.

    Args:
        disputes: List of synthetic dispute dicts from generate_synthetic_disputes()
        concurrency: Max concurrent pipeline executions

    Returns:
        List of result dicts with predicted vs ground truth actions
    """
    service = DisputeService()
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []

    async def _bounded_run(dispute: dict) -> dict[str, Any]:
        async with semaphore:
            return await _run_single_dispute(dispute, service)

    tasks = [_bounded_run(d) for d in disputes]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    return list(results)
