"""
Gate — Conditional Edge Function & Terminal Nodes.

The gate decides the final routing after all evidence analysis is complete:
  - auto_submit:  High confidence, low amount → submit automatically
  - human_review: Uncertain or high-value → require HITL approval
  - accept_loss:  Insufficient evidence → do not contest
  - auto_refund:  Customer is right, low amount → refund automatically  (NEW)
  - refund_review: Customer is right, high amount → require HITL approval (NEW)

Pipeline position: ... → draft_response → [gate_decision] → terminal node → END
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.dispute.agent.state import DisputeAgentState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# GATE — CONDITIONAL EDGE FUNCTION
# ═══════════════════════════════════════════════════════════════════

def gate_decision(state: DisputeAgentState) -> str:
    """
    Conditional edge function for the LangGraph.

    Returns the name of the next node based on:
      - Recommended action (contest / refund_customer / accept_loss)
      - Customer legitimacy signal
      - Winnability score vs threshold
      - Disputed amount vs ceiling

    DEFENSE-ONLY: All money-related decisions are explicitly gated.
    """
    score = state.get("winnability_score", 0.0)
    amount = state.get("disputed_amount_inr", 0)
    recommended = state.get("recommended_action", "contest")
    legitimacy = state.get("customer_legitimacy_signal", False)

    # Accept loss — no point contesting
    if recommended == "accept_loss" or (not legitimacy and score < 0.3):
        return "accept_loss"

    # Refund path — customer is right, bounded by amount gate
    if recommended == "refund_customer" and legitimacy:
        if amount <= settings.auto_refund_amount_ceiling_inr:
            return "auto_refund"
        return "refund_review"

    # Auto-submit — high confidence, low amount
    if (
        score >= settings.auto_submit_score_threshold
        and amount <= settings.auto_submit_amount_ceiling_inr
    ):
        return "auto_submit"

    # Everything else → human review
    return "human_review"


# ═══════════════════════════════════════════════════════════════════
# TERMINAL NODES
# ═══════════════════════════════════════════════════════════════════

async def auto_submit_node(state: DisputeAgentState) -> dict:
    """Mark dispute for automatic submission — high confidence, low amount."""
    return {
        "gate_action": "auto_submit",
        "requires_human_review": False,
        "human_review_reason": None,
        "case_resolution": "resolved_contested",
        "current_node": "auto_submit",
        "node_history": state.get("node_history", []) + ["auto_submit"],
    }


async def human_review_node(state: DisputeAgentState) -> dict:
    """
    HITL node for dispute review — handles both pre-interrupt and post-resume.

    Pre-interrupt (no ``user_decision``):
        Populates review metadata. The graph will be interrupted *before*
        this node actually executes (via ``interrupt_before``), so this
        code only runs after the human resumes the graph.

    Post-resume (``user_decision`` present):
        - ``accept`` → proceed to contest the dispute
        - ``reject`` → accept the loss
    """
    decision = state.get("user_decision")

    if decision and decision.get("action") == "reject":
        return {
            "gate_action": "human_review",
            "requires_human_review": False,
            "human_review_reason": f"Rejected by reviewer: {decision.get('reason', '')}",
            "case_resolution": "resolved_accepted_loss",
            "current_node": "human_review",
            "node_history": state.get("node_history", []) + ["human_review"],
        }

    # Default: accept → proceed with contest
    score = state.get("winnability_score", 0.0)
    amount = state.get("disputed_amount_inr", 0)

    reasons = []
    if amount > 10_000:
        reasons.append(f"High amount: ₹{amount:,}")
    if score < 0.85:
        reasons.append(f"Score below threshold: {score:.0%}")

    return {
        "gate_action": "human_review",
        "requires_human_review": False,
        "human_review_reason": "; ".join(reasons) if reasons else "Manual review requested",
        "case_resolution": "resolved_contested",
        "current_node": "human_review",
        "node_history": state.get("node_history", []) + ["human_review"],
    }


async def accept_loss_node(state: DisputeAgentState) -> dict:
    """Mark dispute as accepted loss — insufficient evidence to contest."""
    return {
        "gate_action": "accept_loss",
        "requires_human_review": False,
        "human_review_reason": None,
        "case_resolution": "resolved_accepted_loss",
        "current_node": "accept_loss",
        "node_history": state.get("node_history", []) + ["accept_loss"],
    }


async def auto_refund_node(state: DisputeAgentState) -> dict:
    """
    Execute refund via Razorpay API — customer is right, low amount.

    Calls the Razorpay Refunds API to issue the refund automatically.
    """
    from app.dispute.agent.nodes._razorpay import execute_razorpay_refund

    payment_id = state.get("payment_id", "")
    amount = state.get("disputed_amount_inr", 0)
    dispute_id = state.get("dispute_id", "UNKNOWN")

    logger.info(
        "Auto-refunding ₹%d for dispute %s (payment %s)",
        amount, dispute_id, payment_id,
    )

    refund_result = await execute_razorpay_refund(
        payment_id=payment_id,
        amount=amount,
        reason=f"Auto-refund for dispute {dispute_id} — customer legitimacy detected",
    )

    return {
        "gate_action": "auto_refund",
        "requires_human_review": False,
        "human_review_reason": None,
        "refund_id": refund_result.get("refund_id"),
        "refund_status": refund_result.get("status", "failed"),
        "case_resolution": "resolved_refunded",
        "current_node": "auto_refund",
        "node_history": state.get("node_history", []) + ["auto_refund"],
    }


async def refund_review_node(state: DisputeAgentState) -> dict:
    """
    HITL node for refund review — handles both pre-interrupt and post-resume.

    Pre-interrupt (no ``user_decision``):
        Populates review metadata. The graph will be interrupted *before*
        this node (via ``interrupt_before``), so this code only runs
        after the human resumes.

    Post-resume (``user_decision`` present):
        - ``accept`` → execute the refund via Razorpay
        - ``reject`` → reject the refund, accept the loss
    """
    decision = state.get("user_decision")
    amount = state.get("disputed_amount_inr", 0)

    if decision and decision.get("action") == "reject":
        return {
            "gate_action": "refund_review",
            "requires_human_review": False,
            "human_review_reason": f"Refund rejected by reviewer: {decision.get('reason', '')}",
            "refund_id": None,
            "refund_status": None,
            "case_resolution": "resolved_accepted_loss",
            "current_node": "refund_review",
            "node_history": state.get("node_history", []) + ["refund_review"],
        }

    # Accept → execute the refund
    from app.dispute.agent.nodes._razorpay import execute_razorpay_refund

    payment_id = state.get("payment_id", "")
    dispute_id = state.get("dispute_id", "UNKNOWN")

    logger.info(
        "Reviewer approved refund of ₹%d for dispute %s (payment %s)",
        amount, dispute_id, payment_id,
    )

    refund_result = await execute_razorpay_refund(
        payment_id=payment_id,
        amount=amount,
        reason=f"Human-approved refund for dispute {dispute_id}",
    )

    return {
        "gate_action": "refund_review",
        "requires_human_review": False,
        "human_review_reason": (
            f"Refund approved by reviewer for ₹{amount:,}"
        ),
        "refund_id": refund_result.get("refund_id"),
        "refund_status": refund_result.get("status", "failed"),
        "case_resolution": "resolved_refunded",
        "current_node": "refund_review",
        "node_history": state.get("node_history", []) + ["refund_review"],
    }
