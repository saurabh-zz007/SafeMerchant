"""
Super Step 3 — Draft Response Letter.

Runs a 3-step pipeline for the contest path:
  Step A: Extract structured facts from customer communications (LLM)
  Step B: Draft evidence response with grounded claims (LLM)
  Step C: Verify grounding deterministically (no LLM)

For refund/accept_loss paths, passes through with minimal state updates.

Pipeline position: ... → triage_and_score → [draft_response] → gate_decision → ...
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.dispute.agent.nodes._llm import get_llm
from app.dispute.agent.nodes._reason_code_map import get_required_evidence_fields
from app.dispute.agent.nodes._verification import (
    rebuild_letter_from_verified_fields,
    verify_grounding,
)
from app.dispute.agent.state import DisputeAgentState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# STEP A — Communications Extraction
# ═══════════════════════════════════════════════════════════════════

COMMS_EXTRACTION_PROMPT = """You are analyzing customer communications for a payment dispute.

Given the following customer communication transcripts, extract these facts:
1. acknowledged_receipt: Did the customer acknowledge receiving the product? (true/false)
2. complaint_before_dispute: Did the customer raise a complaint before filing the formal dispute? (true/false)
3. relevant_quote_ref: The most relevant verbatim quote from the transcript that supports the merchant's defense case.

Communications:
{communications_json}

Respond with valid JSON matching this exact schema:
{{
  "acknowledged_receipt": true/false,
  "complaint_before_dispute": true/false,
  "relevant_quote_ref": "exact quote from transcript"
}}"""


async def _step_a_extract_comms(communications: list[dict]) -> dict | None:
    """Step A: Extract structured facts from communications via LLM."""
    if not communications:
        return {
            "acknowledged_receipt": False,
            "complaint_before_dispute": False,
            "relevant_quote_ref": "",
        }

    try:
        from app.dispute.schemas.dispute_analysis import CommsExtraction

        llm = get_llm()
        structured_llm = llm.with_structured_output(CommsExtraction)

        comms_json = json.dumps(communications, default=str, indent=2)
        result = await structured_llm.ainvoke(
            COMMS_EXTRACTION_PROMPT.format(communications_json=comms_json)
        )
        return result.model_dump()
    except Exception as e:
        logger.warning("Step A (comms extraction) failed: %s — using defaults", e)
        return {
            "acknowledged_receipt": False,
            "complaint_before_dispute": False,
            "relevant_quote_ref": "",
        }


# ═══════════════════════════════════════════════════════════════════
# STEP B — LLM Draft Generation
# ═══════════════════════════════════════════════════════════════════

DRAFT_PROMPT = """You are a chargeback defense specialist writing a response to a payment dispute.

DISPUTE DETAILS:
- Dispute ID: {dispute_id}
- Order ID: {order_id}
- Reason Code: {reason_code}
- Disputed Amount: ₹{amount}

REQUIRED EVIDENCE FIELDS for this reason code: {required_fields}

FULL EVIDENCE BUNDLE:
{evidence_json}

COMMUNICATIONS ANALYSIS:
{comms_extraction_json}

INSTRUCTIONS:
1. Write a concise summary (1-2 sentences).
2. Write an explanation_letter (MUST be ≤1000 characters) addressed to the bank.
3. For each required evidence field, list the specific factual claims that support the merchant's case.
   CRITICAL: Every fact MUST include:
   - claim: the factual statement
   - source_key: the dotted path in the evidence bundle (e.g., "shipping.delivery_status")
   - source_value: the exact value from the evidence at that path

Only cite facts that exist in the evidence bundle. Do NOT fabricate evidence.

Respond with valid JSON matching this schema:
{{
  "summary": "...",
  "explanation_letter": "...",
  "evidence_fields": {{
    "field_name": {{
      "facts": [
        {{"claim": "...", "source_key": "...", "source_value": "..."}}
      ]
    }}
  }}
}}"""


async def _step_b_draft_response(
    state: DisputeAgentState,
    evidence: dict,
    comms_extraction: dict,
    required_fields: list[str],
) -> dict | None:
    """Step B: Generate structured draft response via LLM."""
    try:
        from app.dispute.schemas.dispute_analysis import DraftOutput

        llm = get_llm()
        structured_llm = llm.with_structured_output(DraftOutput)

        prompt = DRAFT_PROMPT.format(
            dispute_id=state.get("dispute_id", "UNKNOWN"),
            order_id=state.get("order_id", "UNKNOWN"),
            reason_code=state.get("reason_code", "unknown"),
            amount=state.get("disputed_amount_inr", 0),
            required_fields=", ".join(required_fields),
            evidence_json=json.dumps(evidence, default=str, indent=2),
            comms_extraction_json=json.dumps(comms_extraction, default=str, indent=2),
        )

        result = await structured_llm.ainvoke(prompt)
        return result.model_dump()
    except Exception as e:
        logger.warning("Step B (LLM draft) failed: %s — falling back to template", e)
        return None


# ═══════════════════════════════════════════════════════════════════
# MAIN NODE FUNCTION
# ═══════════════════════════════════════════════════════════════════

async def draft_response(state: DisputeAgentState) -> dict[str, Any]:
    """
    Draft a bank-compliant evidence letter for the dispute.

    For the contest path: runs Steps A → B → C.
    For refund/accept_loss: minimal pass-through.
    """
    evidence = state.get("evidence_bundle")
    recommended_action = state.get("recommended_action", "contest")
    dispute_id = state.get("dispute_id", "UNKNOWN")

    base_update = {
        "current_node": "draft_response",
        "node_history": state.get("node_history", []) + ["draft_response"],
    }

    # ── Non-contest paths: minimal pass-through ──
    if recommended_action in ("refund_customer", "accept_loss") or evidence is None:
        reason = {
            "refund_customer": "Customer legitimacy detected — skipping draft, proceeding to refund.",
            "accept_loss": "Accept loss — no evidence to draft response.",
        }.get(recommended_action, "No evidence available.")

        return {
            **base_update,
            "comms_extraction": None,
            "draft_summary": reason,
            "draft_explanation_letter": None,
            "draft_evidence_fields": None,
            "verification_report": None,
            "verified_explanation_letter": None,
            "verified_evidence_fields": None,
            "draft_response_letter": None,
            "cited_evidence_keys": [],
        }

    # ── Contest path: Steps A → B → C ──

    # Step A: Extract structured facts from communications
    comms = evidence.get("communications", [])
    comms_extraction = await _step_a_extract_comms(comms)
    logger.info("Step A complete — comms extraction: %s", comms_extraction)

    # Step B: LLM draft generation
    reason_code = state.get("reason_code", "chargeback")
    required_fields = get_required_evidence_fields(reason_code)

    draft_output = await _step_b_draft_response(
        state, evidence, comms_extraction or {}, required_fields
    )

    if draft_output is None:
        # Fallback to template-based draft
        return {
            **base_update,
            **_template_fallback(state, evidence),
            "comms_extraction": comms_extraction,
        }

    draft_summary = draft_output.get("summary", "")
    draft_letter = draft_output.get("explanation_letter", "")
    draft_fields = draft_output.get("evidence_fields", {})

    # Step C: Grounding verification
    verified_fields, verification_report, cited_keys = verify_grounding(
        draft_fields, evidence
    )

    # Rebuild letter using only verified facts
    verified_letter = rebuild_letter_from_verified_fields(
        verified_fields, draft_letter, dispute_id
    )

    logger.info(
        "Draft pipeline complete — %d/%d claims verified",
        verification_report.get("verified_claims", 0),
        verification_report.get("total_claims", 0),
    )

    return {
        **base_update,
        "comms_extraction": comms_extraction,
        "draft_summary": draft_summary,
        "draft_explanation_letter": draft_letter,
        "draft_evidence_fields": draft_fields,
        "verification_report": verification_report,
        "verified_explanation_letter": verified_letter,
        "verified_evidence_fields": verified_fields,
        "draft_response_letter": verified_letter,  # Legacy field — use verified version
        "cited_evidence_keys": cited_keys,
    }


def _template_fallback(state: DisputeAgentState, evidence: dict) -> dict[str, Any]:
    """
    Template-based fallback when LLM draft fails.
    Preserves the original template logic from before the LLM rewrite.
    """
    score = state.get("winnability_score", 0.0)
    dispute_id = state.get("dispute_id", "UNKNOWN")
    order_id = state.get("order_id", "UNKNOWN")

    cited_keys = []
    letter_parts = [
        f"# Dispute Response — {dispute_id}",
        f"**Order ID:** {order_id}",
        f"**Winnability Score:** {score:.0%}",
        "",
        "## Evidence Summary",
    ]

    order = evidence.get("order", {})
    if order:
        cited_keys.append("order")
        letter_parts.append(
            f"- **Order:** {order.get('item_description', 'N/A')} — "
            f"₹{order.get('amount_inr', 0):,} on {order.get('created_at', 'N/A')}"
        )

    shipping = evidence.get("shipping")
    if shipping:
        cited_keys.append("shipping")
        letter_parts.append(
            f"- **Delivery:** {shipping.get('delivery_status', 'Unknown')} via "
            f"{shipping.get('courier_partner', 'N/A')} "
            f"(Tracking: {shipping.get('tracking_id', 'N/A')})"
        )
        if shipping.get("signed_by"):
            letter_parts.append(f"  - Signed by: {shipping['signed_by']}")

    comms = evidence.get("communications", [])
    if comms:
        cited_keys.append("communications")
        letter_parts.append(f"- **Customer Communications:** {len(comms)} interaction(s) on file")

    risk = evidence.get("risk_signals")
    if risk:
        cited_keys.append("risk_signals")
        letter_parts.append(
            f"- **Authentication:** 2FA={'Verified' if risk.get('is_2fa_verified') else 'Not verified'}, "
            f"Account age: {risk.get('account_age_days', 0)} days"
        )

    letter_parts.extend([
        "",
        "## Recommendation",
        f"Based on the evidence, we recommend **{'contesting' if score >= 0.5 else 'accepting'}** "
        f"this dispute with a winnability confidence of {score:.0%}.",
    ])

    return {
        "draft_summary": f"Template-based draft for dispute {dispute_id}",
        "draft_explanation_letter": "\n".join(letter_parts),
        "draft_evidence_fields": None,
        "verification_report": None,
        "verified_explanation_letter": None,
        "verified_evidence_fields": None,
        "draft_response_letter": "\n".join(letter_parts),
        "cited_evidence_keys": cited_keys,
    }
