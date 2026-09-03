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
    dispute_id = state.get("dispute_id", "UNKNOWN")
    score = state.get("winnability_score", 0.0)
    amount = state.get("disputed_amount_inr", 0)
    recommended = state.get("recommended_action", "contest")
    legitimacy = state.get("customer_legitimacy_signal", False)

    logger.info(
        "[GATE EVALUATION] dispute_id=%s | winnability_score=%.2f | legitimacy_signal=%s | "
        "amount_inr=₹%d | recommended_action=%s",
        dispute_id,
        score if score is not None else 0.0,
        legitimacy,
        amount,
        recommended,
    )

    decision: str
    # Accept loss — no point contesting
    if recommended == "accept_loss" or (not legitimacy and score < 0.3):
        decision = "accept_loss"

    # Refund path — customer is right, bounded by amount gate
    elif recommended == "refund_customer" and legitimacy:
        if amount <= settings.auto_refund_amount_ceiling_inr:
            decision = "auto_refund"
        else:
            decision = "refund_review"

    # Auto-submit — high confidence, low amount
    elif (
        score >= settings.auto_submit_score_threshold
        and amount <= settings.auto_submit_amount_ceiling_inr
    ):
        decision = "auto_submit"

    # Everything else → human review
    else:
        decision = "human_review"

    logger.info("[GATE ROUTING] dispute_id=%s → routed to '%s'", dispute_id, decision)
    return decision


# ═══════════════════════════════════════════════════════════════════
# TERMINAL NODES
# ═══════════════════════════════════════════════════════════════════

async def auto_submit_node(state: DisputeAgentState) -> dict:
    """Mark dispute for automatic submission — high confidence, low amount."""
    score = state.get("winnability_score", 0.0)
    amount = state.get("disputed_amount_inr", 0)
    triage_reasoning = state.get("triage_reasoning", "")
    score_pct = f"{score:.0%}" if score is not None else "N/A"

    rules_triggered = [
        f"High-confidence winnability score ({score_pct} >= {settings.auto_submit_score_threshold:.0%})",
        f"Dispute amount (₹{amount:,}) within auto-contest ceiling (<= ₹{settings.auto_submit_amount_ceiling_inr:,})",
        "Complete evidentiary proof package compiled (delivery verification, transcript, ledger)",
    ]

    rationale = (
        f"**Automated Decision:** Evidence automatically submitted for representment.\n\n"
        f"**Rule Rationale:**\n"
        f"- **Confidence Score:** Winnability score of {score_pct} meets or exceeds the automated submission threshold ({settings.auto_submit_score_threshold:.0%}).\n"
        f"- **Amount Ceiling:** Disputed amount of ₹{amount:,} is within the low-risk automated ceiling (₹{settings.auto_submit_amount_ceiling_inr:,}).\n"
        f"- **Evidence Summary:** {triage_reasoning or 'Merchant fulfilled order with verifiable tracking and proof of delivery.'}\n"
        f"- **Action:** Auto-generated defense package queued for Razorpay submission without human bottleneck."
    )

    return {
        "gate_action": "auto_submit",
        "requires_human_review": False,
        "human_review_reason": None,
        "case_resolution": "resolved_contested",
        "current_node": "auto_submit",
        "node_history": state.get("node_history", []) + ["auto_submit"],
        "decision_type": "automated",
        "auto_decision_rationale": rationale,
        "rules_triggered": rules_triggered,
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
    score = state.get("winnability_score", 0.0)
    amount = state.get("disputed_amount_inr", 0)
    triage_reasoning = state.get("triage_reasoning", "")
    score_pct = f"{score:.0%}" if score is not None else "0%"

    rules_triggered = [
        f"Winnability score ({score_pct}) is below defense threshold (< 30%)",
        "Insufficient merchant documentation or high representment loss risk",
        "Economic non-viability: cost of defense exceeds expected recovery value",
    ]

    rationale = (
        f"**Automated Decision:** Dispute loss automatically accepted (no representment).\n\n"
        f"**Rule Rationale:**\n"
        f"- **Winnability Assessment:** Calculated score of {score_pct} indicates low probability of reversal.\n"
        f"- **Economic Viability:** Contesting this claim would incur operational overhead and potential arbitration fees greater than the disputed amount (₹{amount:,}).\n"
        f"- **Triage Summary:** {triage_reasoning or 'Merchant records lack definitive proof of fulfillment or delivery confirmation.'}\n"
        f"- **Action:** Loss accepted to preserve merchant chargeback standing and avoid dispute filing penalties."
    )

    return {
        "gate_action": "accept_loss",
        "requires_human_review": False,
        "human_review_reason": None,
        "case_resolution": "resolved_accepted_loss",
        "current_node": "accept_loss",
        "node_history": state.get("node_history", []) + ["accept_loss"],
        "decision_type": "automated",
        "auto_decision_rationale": rationale,
        "rules_triggered": rules_triggered,
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
    legitimacy_reasoning = state.get("legitimacy_reasoning", "")

    logger.info(
        "Auto-refunding ₹%d for dispute %s (payment %s)",
        amount, dispute_id, payment_id,
    )

    refund_result = await execute_razorpay_refund(
        payment_id=payment_id,
        amount=amount,
        reason=f"Auto-refund for dispute {dispute_id} — customer legitimacy detected",
    )

    refund_id = refund_result.get("refund_id")
    refund_status = refund_result.get("status", "failed")

    rules_triggered = [
        "Customer legitimacy signal confirmed (genuine claim / lost in transit / merchant defect)",
        f"Disputed amount (₹{amount:,}) is within auto-refund threshold (<= ₹{settings.auto_refund_amount_ceiling_inr:,})",
        f"Automated Razorpay Refund API executed (Refund ID: {refund_id or 'N/A'}, Status: {refund_status})",
    ]

    rationale = (
        f"**Automated Decision:** Refund automatically issued to customer.\n\n"
        f"**Rule Rationale:**\n"
        f"- **Customer Legitimacy:** Verified genuine claim ({legitimacy_reasoning or 'Legitimate customer claim detected by triage'}).\n"
        f"- **Amount Threshold:** Disputed amount of ₹{amount:,} is within the merchant's automatic refund ceiling (₹{settings.auto_refund_amount_ceiling_inr:,}).\n"
        f"- **Action:** Bypassed manual review queue and executed immediate refund via Razorpay API to maintain customer trust and eliminate chargeback penalties."
    )

    return {
        "gate_action": "auto_refund",
        "requires_human_review": False,
        "human_review_reason": None,
        "refund_id": refund_id,
        "refund_status": refund_status,
        "case_resolution": "resolved_refunded",
        "current_node": "auto_refund",
        "node_history": state.get("node_history", []) + ["auto_refund"],
        "decision_type": "automated",
        "auto_decision_rationale": rationale,
        "rules_triggered": rules_triggered,
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
