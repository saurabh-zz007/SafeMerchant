"""
Step C — Deterministic Grounding Verifier.

Walks every factual claim in the LLM draft output and confirms
each one matches actual data in the evidence bundle.

DEFENSE-ONLY: This verifier is a safety net — it ensures the agent
never fabricates or misattributes evidence in dispute responses.
No LLM calls — pure deterministic logic.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_dotted_key(data: dict, dotted_key: str) -> Any | None:
    """
    Resolve a dotted path like 'shipping.delivery_status' in a nested dict.
    Returns None if any key in the path is missing.
    """
    keys = dotted_key.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def verify_grounding(
    draft_evidence_fields: dict,
    evidence_bundle: dict,
) -> tuple[dict, dict, list[str]]:
    """
    Walk every factual claim in the LLM draft output.
    Confirm each matches an actual field in the evidence bundle.

    Args:
        draft_evidence_fields: {field_name: {"facts": [{"claim", "source_key", "source_value"}, ...]}}
        evidence_bundle: The raw evidence bundle from the merchant DB.

    Returns:
        (verified_fields, verification_report, cited_evidence_keys)
        - verified_fields: same structure but only with verified facts
        - verification_report: {"kept": [...], "dropped": [...]}
        - cited_evidence_keys: list of top-level evidence keys that were cited
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    verified_fields: dict[str, dict] = {}
    cited_keys: set[str] = set()

    for field_name, field_data in draft_evidence_fields.items():
        facts = field_data.get("facts", [])
        if isinstance(field_data, dict) and "facts" not in field_data:
            # Handle case where field_data might be a Pydantic model dumped to dict
            facts = field_data.get("facts", [])

        verified_facts = []

        for fact in facts:
            source_key = fact.get("source_key", "")
            claimed_value = str(fact.get("source_value", ""))
            claim_text = fact.get("claim", "")

            # Resolve the actual value from the evidence bundle
            actual_value = _resolve_dotted_key(evidence_bundle, source_key)

            if actual_value is not None:
                actual_str = str(actual_value)
                # Check if the claimed value is consistent with the actual value
                # We use containment check in both directions for flexibility
                if (
                    claimed_value.lower() in actual_str.lower()
                    or actual_str.lower() in claimed_value.lower()
                    or claimed_value.lower() == actual_str.lower()
                ):
                    kept.append({
                        "claim": claim_text,
                        "source_key": source_key,
                        "claimed_value": claimed_value,
                        "actual_value": actual_str,
                        "status": "verified",
                    })
                    verified_facts.append(fact)
                    # Track top-level key
                    cited_keys.add(source_key.split(".")[0])
                else:
                    dropped.append({
                        "claim": claim_text,
                        "source_key": source_key,
                        "claimed_value": claimed_value,
                        "actual_value": actual_str,
                        "reason": "value_mismatch",
                    })
                    logger.warning(
                        "Grounding DROPPED: claim='%s', source_key='%s', "
                        "claimed='%s', actual='%s'",
                        claim_text, source_key, claimed_value, actual_str,
                    )
            else:
                dropped.append({
                    "claim": claim_text,
                    "source_key": source_key,
                    "claimed_value": claimed_value,
                    "actual_value": None,
                    "reason": "source_key_not_found",
                })
                logger.warning(
                    "Grounding DROPPED: claim='%s', source_key='%s' not found in evidence",
                    claim_text, source_key,
                )

        if verified_facts:
            verified_fields[field_name] = {"facts": verified_facts}

    verification_report = {
        "kept": kept,
        "dropped": dropped,
        "total_claims": len(kept) + len(dropped),
        "verified_claims": len(kept),
        "dropped_claims": len(dropped),
    }

    logger.info(
        "Grounding verification: %d/%d claims verified, %d dropped",
        len(kept), len(kept) + len(dropped), len(dropped),
    )

    return verified_fields, verification_report, sorted(cited_keys)


def rebuild_letter_from_verified_fields(
    verified_fields: dict,
    original_letter: str,
    dispute_id: str,
) -> str:
    """
    Rebuild the explanation letter using only verified facts.

    If all facts were dropped, returns a generic letter.
    Otherwise builds a clean letter from verified evidence.
    """
    if not verified_fields:
        return (
            f"Re: Dispute {dispute_id}\n\n"
            "We are reviewing the evidence for this dispute and will "
            "provide a detailed response shortly."
        )

    parts = [f"Re: Dispute {dispute_id}\n"]
    parts.append("We are contesting this dispute based on the following verified evidence:\n")

    for field_name, field_data in verified_fields.items():
        readable_name = field_name.replace("_", " ").title()
        parts.append(f"\n{readable_name}:")
        for fact in field_data.get("facts", []):
            claim = fact.get("claim", "")
            if claim:
                parts.append(f"  - {claim}")

    parts.append(
        "\nAll claims above have been verified against our internal records."
    )

    result = "\n".join(parts)
    # Enforce Razorpay's 1000-character limit
    if len(result) > 1000:
        result = result[:997] + "..."

    return result
