"""
Static mapping: dispute reason code → required evidence fields.

Per Razorpay's dispute documentation, each reason code requires specific
types of evidence to be submitted. This map drives the LLM prompt in
super_step_3 so it knows which evidence fields to populate.
"""

from __future__ import annotations


REASON_CODE_EVIDENCE_MAP: dict[str, list[str]] = {
    "chargeback":               ["shipping_proof", "explanation_letter"],
    "fraud":                    ["customer_communication", "explanation_letter"],
    "product_not_received":     ["shipping_proof", "customer_communication", "explanation_letter"],
    "product_not_as_described": ["customer_communication", "explanation_letter"],
    "duplicate":                ["billing_proof", "explanation_letter"],
    "subscription_cancelled":   ["cancellation_proof", "customer_communication", "explanation_letter"],
}


def get_required_evidence_fields(reason_code: str) -> list[str]:
    """
    Get the list of evidence fields required for a given reason code.
    Falls back to ["explanation_letter"] if the reason code is unknown.
    """
    return REASON_CODE_EVIDENCE_MAP.get(
        reason_code,
        ["explanation_letter"],
    )
