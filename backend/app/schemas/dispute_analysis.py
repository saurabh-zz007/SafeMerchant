"""
Pydantic models for dispute analysis output.

Used by API responses and the evaluation harness.
"""

from pydantic import BaseModel, Field


class DisputeAnalysisOutput(BaseModel):
    """High-level analysis output for a processed dispute."""

    is_fraud: bool = Field(
        description="True if the customer has a genuine problem and should be refunded."
    )
    winnability_score: float = Field(
        description="A float from 0.0 to 1.0 indicating merchant win probability."
    )
    suggested_action: str = Field(
        description="Detailed action plan or explanation of the decision."
    )
    customer_legitimacy: bool = Field(
        default=False,
        description="True if the customer legitimacy check flagged this case."
    )
    case_resolution: str = Field(
        default="pending",
        description="Resolution status: resolved_contested | resolved_refunded | resolved_accepted_loss | pending_review"
    )