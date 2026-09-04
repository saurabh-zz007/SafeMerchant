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
    Handles timezone-aware and timezone-naive comparisons safely in UTC.
    """
    if not comms:
        return False

    # Determine the cutoff timestamp
    cutoff: Optional[datetime] = None
    if dispute_created_at:
        cutoff = datetime.fromtimestamp(dispute_created_at, tz=timezone.utc)
    elif order_created_at:
        try:
            ord_dt = datetime.fromisoformat(order_created_at)
            if ord_dt.tzinfo is None:
                ord_dt = ord_dt.replace(tzinfo=timezone.utc)
            cutoff = ord_dt
        except (ValueError, TypeError):
            return False

    if cutoff is None:
        return False

    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    for comm in comms:
        logged_at_str = comm.get("logged_at")
        if not logged_at_str:
            continue
        try:
            logged_at = datetime.fromisoformat(logged_at_str)
            if logged_at.tzinfo is None:
                logged_at = logged_at.replace(tzinfo=timezone.utc)
            if logged_at < cutoff:
                return True
            # Fallback if dispute_created_at timestamp was set equal or before order_created_at in mock payloads
            if order_created_at:
                ord_dt = datetime.fromisoformat(order_created_at).replace(tzinfo=timezone.utc)
                if cutoff <= ord_dt and logged_at >= ord_dt:
                    return True
        except (ValueError, TypeError):
            continue

    return False


async def triage_and_score(state: DisputeAgentState) -> dict[str, Any]:
    """
    Analyze evidence, assign a winnability score, and check customer legitimacy.

    Scoring is heuristic-based with rule-based adjustments for liability shift
    (e.g., fraud disputes without 2FA). The legitimacy check runs independently
    to detect cases where the customer genuinely deserves a refund (e.g., no
    delivery proof + pre-existing complaint).
    """
    evidence = state.get("evidence_bundle")
    reason_code = state.get("reason_code", "chargeback")

    if evidence is None:
        return {
            "winnability_score": 0.0,
            "risk_factors": ["missing_order_record", "no_merchant_evidence"],
            "triage_reasoning": (
                "⚠️ Strict Defense-Only Failsafe: No order or payment records found in the merchant database. "
                "Not enough data is available to solve or defend this dispute. Auto-refunds strictly blocked."
            ),
            "recommended_action": "accept_loss",
            "customer_legitimacy_signal": False,
            "legitimacy_reasoning": "Cannot assess customer legitimacy without merchant order records.",
            "current_node": "triage_and_score",
            "node_history": state.get("node_history", []) + ["triage_and_score"],
        }

    # ── Winnability scoring logic ──
    score = 0.5
    risk_factors = []

    # Physical delivery proof (support both schema naming conventions)
    shipping = evidence.get("shipping") or evidence.get("shipping_proof")
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

    # Customer communication (support both schema naming conventions)
    comms = evidence.get("communications") or evidence.get("customer_communication") or []
    if isinstance(comms, dict):
        comms = [comms]

    if comms:
        has_positive_comm = False
        has_vague_comm = False
        for c in comms:
            transcript = (c.get("message_transcript") or "").lower()
            if any(w in transcript for w in ["thanks", "fit perfectly", "great", "received", "works"]):
                has_positive_comm = True
            elif any(w in transcript for w in ["doesnt look right", "no response"]):
                has_vague_comm = True

        if has_positive_comm:
            score += 0.05
        elif has_vague_comm and reason_code == "fraud":
            score -= 0.1
            risk_factors.append("vague_or_suspicious_communication")
    else:
        score -= 0.05
        risk_factors.append("no_customer_communication")

    # Special handling for Fraud disputes without 2FA liability shift:
    # Under card network chargeback rules (Visa Core Rules / Mastercard Chargeback Guide),
    # physical delivery alone cannot defend a fraud dispute without 3DS/2FA liability shift.
    if reason_code == "fraud":
        if not (risk and risk.get("is_2fa_verified")):
            score = min(score, 0.2)
            risk_factors.append("fraud_without_2fa_liability_shift")

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
