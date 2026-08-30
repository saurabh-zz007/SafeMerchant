"""
Pydantic models for LLM structured output in the dispute pipeline.

Step A: CommsExtraction — structured facts from customer communications.
Step B: DraftOutput — complete LLM-generated draft with grounded evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# STEP A — Communications Extraction
# ═══════════════════════════════════════════════════════════════════

class CommsExtraction(BaseModel):
    """Step A output — structured facts extracted from communications."""

    acknowledged_receipt: bool = Field(
        description="True if the customer acknowledged receiving the product in any communication"
    )
    complaint_before_dispute: bool = Field(
        description="True if the customer raised a complaint before filing the dispute"
    )
    relevant_quote_ref: str = Field(
        description="The most relevant verbatim quote from the transcript that supports the merchant's case"
    )


# ═══════════════════════════════════════════════════════════════════
# STEP B — LLM Draft Output
# ═══════════════════════════════════════════════════════════════════

class EvidenceFact(BaseModel):
    """A single grounded factual claim."""

    claim: str = Field(
        description="The factual statement (e.g., 'Product was delivered on 2026-08-13')"
    )
    source_key: str = Field(
        description="Which evidence field this comes from (e.g., 'shipping.delivery_status')"
    )
    source_value: str = Field(
        description="The actual value from the evidence bundle that supports this claim"
    )


class DraftEvidenceField(BaseModel):
    """LLM draft output for one evidence field."""

    facts: list[EvidenceFact] = Field(
        description="List of grounded factual claims for this evidence field"
    )


class DraftOutput(BaseModel):
    """Step B output — complete LLM draft with grounded evidence."""

    summary: str = Field(
        description="Short-form summary of the dispute analysis (1-2 sentences)"
    )
    explanation_letter: str = Field(
        max_length=1000,
        description="Bank-compliant explanation letter (≤1000 chars per Razorpay limit)"
    )
    evidence_fields: dict[str, DraftEvidenceField] = Field(
        description="Evidence organized by field type (e.g., 'shipping_proof', 'customer_communication')"
    )
