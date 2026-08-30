"""
Super Step 2 — Triage & Scoring.

Analyze the evidence and assign a winnability score.
Also performs a customer legitimacy check to detect cases where
the customer genuinely deserves a refund.

Pipeline position: ... → retrieve_evidence → [triage_and_score] → draft_response → ...
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.dispute.agent.state import DisputeAgentState


def _has_complaint_before_dispute(
    comms: list[dict],
    dispute_created_at: Optional[int],
    order_created_at: Optional[str],
) -> bool:
    """
    Check if any customer communication was logged before the dispute was filed.

    Falls back to comparing against order created_at if dispute_created_at is None.
    """
    if not comms:
        return False

    # Determine the cutoff timestamp
    cutoff: Optional[datetime] = None
    if dispute_created_at:
        cutoff = datetime.fromtimestamp(dispute_created_at, tz=timezone.utc)
    elif order_created_at:
        try:
            cutoff = datetime.fromisoformat(order_created_at)
            # Add a generous buffer — comms within 14 days of order are "pre-dispute"
            # This is a heuristic fallback when we don't have the dispute timestamp
        except (ValueError, TypeError):
            return False

    if cutoff is None:
        return False

    for comm in comms:
        logged_at_str = comm.get("logged_at")
        if not logged_at_str:
            continue
        try:
            logged_at = datetime.fromisoformat(logged_at_str)
            if logged_at < cutoff:
                return True
        except (ValueError, TypeError):
            continue

    return False


async def triage_and_score(state: DisputeAgentState) -> dict[str, Any]:
    """
    Analyze evidence, assign a winnability score, and check customer legitimacy.

    Scoring is currently heuristic-based. The legitimacy check runs independently
    to detect cases where the customer genuinely deserves a refund (e.g., no
    delivery proof + pre-existing complaint).
    """
    evidence = state.get("evidence_bundle")

    if evidence is None:
        return {
            "winnability_score": 0.0,
            "risk_factors": ["no_evidence_found"],
            "triage_reasoning": "No evidence was found in the merchant database.",
            "recommended_action": "accept_loss",
            "customer_legitimacy_signal": False,
            "legitimacy_reasoning": "No evidence to assess legitimacy.",
            "current_node": "triage_and_score",
            "node_history": state.get("node_history", []) + ["triage_and_score"],
        }

    # ── Winnability scoring logic ──
    score = 0.5
    risk_factors = []

    # Physical delivery proof
    shipping = evidence.get("shipping")
    if shipping and shipping.get("delivery_status") == "Delivered":
        score += 0.25
        if shipping.get("signed_by"):
            score += 0.1
    else:
        score -= 0.2  # Significant penalty for no delivery proof
        risk_factors.append("no_delivery_proof")

    # 2FA verification
    risk = evidence.get("risk_signals")
    if risk and risk.get("is_2fa_verified"):
        score += 0.1
    else:
        score -= 0.05
        risk_factors.append("no_2fa_verification")

    # Customer communication showing product usage
    comms = evidence.get("communications", [])
    if comms:
        score += 0.05
    else:
        score -= 0.05
        risk_factors.append("no_customer_communication")

    score = max(0.0, min(score, 1.0))

    # ── Legitimacy check (independent of winnability) ──
    has_delivery_proof = (
        shipping is not None
        and shipping.get("delivery_status") == "Delivered"
    )
    has_pre_dispute_complaint = _has_complaint_before_dispute(
        comms,
        state.get("dispute_created_at"),
        evidence.get("order", {}).get("created_at"),
    )

    customer_legitimacy_signal = (not has_delivery_proof) and has_pre_dispute_complaint

    legitimacy_reasons = []
    if not has_delivery_proof:
        legitimacy_reasons.append("No delivery proof on file")
    if has_pre_dispute_complaint:
        legitimacy_reasons.append("Customer complained before filing dispute")
    if customer_legitimacy_signal:
        legitimacy_reasons.append("→ Customer appears to have a legitimate claim")

    legitimacy_reasoning = "; ".join(legitimacy_reasons) if legitimacy_reasons else None

    # ── Determine recommended action ──
    if customer_legitimacy_signal:
        recommended_action = "refund_customer"
    elif score >= settings.auto_submit_score_threshold:
        recommended_action = "contest"
    elif score >= 0.4:
        recommended_action = "contest"  # but may need human review based on amount
    else:
        recommended_action = "accept_loss"

    return {
        "winnability_score": round(score, 2),
        "risk_factors": risk_factors,
        "triage_reasoning": (
            f"Heuristic score: {score:.0%}. Risk factors: {risk_factors}. "
            f"Legitimacy: {'customer appears right' if customer_legitimacy_signal else 'merchant case'}."
        ),
        "recommended_action": recommended_action,
        "customer_legitimacy_signal": customer_legitimacy_signal,
        "legitimacy_reasoning": legitimacy_reasoning,
        "current_node": "triage_and_score",
        "node_history": state.get("node_history", []) + ["triage_and_score"],
    }
