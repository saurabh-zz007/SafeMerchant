"""
Pydantic schemas for the Developer Option: Create Test Dispute scenario builder.
"""

from typing import Optional
from pydantic import BaseModel, Field


class CreateTestDisputeRequest(BaseModel):
    """Input parameters for constructing a synthetic dispute scenario."""

    amount_inr: int = Field(
        ...,
        gt=0,
        description="Disputed transaction amount in INR (e.g. 2999)",
    )
    item_description: str = Field(
        default="Wireless Noise-Canceling Headphones",
        description="Item / product description (cosmetic only)",
    )
    delivery_status: str = Field(
        default="Delivered (Signed)",
        description=(
            "Delivery status: 'Delivered (Signed)', 'Delivered (No Signature)', "
            "'Lost in Transit', 'In Transit'"
        ),
    )
    customer_communication: str = Field(
        default="No communication on file",
        description=(
            "Customer interaction status: 'Customer confirms receipt', "
            "'Customer disputes receipt', 'No communication on file'"
        ),
    )
    is_2fa_verified: bool = Field(
        default=True,
        description="Whether payment was authenticated with 2FA/OTP",
    )
    account_age_days: int = Field(
        default=180,
        ge=0,
        description="Customer account age in days",
    )
    reason_code: str = Field(
        default="product_not_received",
        description="Razorpay dispute reason code",
    )

    model_config = {"extra": "ignore"}


class CreateTestDisputeResponse(BaseModel):
    """Response returned when a test dispute is generated and submitted to webhook pipeline."""

    status: str = Field(default="success")
    dispute_id: str = Field(..., description="Generated Razorpay dispute ID (e.g., disp_...)")
    order_id: str = Field(..., description="Generated merchant order ID (e.g., ORD_...)")
    payment_id: str = Field(..., description="Generated Razorpay payment ID (e.g., pay_...)")
    message: str = Field(default="Dispute scenario created and dispatched to webhook pipeline.")

    model_config = {"extra": "ignore"}
