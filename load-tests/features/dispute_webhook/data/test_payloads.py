"""
Test dataset builder for the 5 Gate-Decision coverage dispute scenarios.
Matches the current PostgreSQL seed database schema & Razorpay webhook payload structure.

Gate Decisions Tested:
1. ORD_2001 -> AUTO_REFUND (Legitimate claim, low value <= ₹5,000)
2. ORD_2002 -> REFUND_REVIEW (Legitimate claim, high value > ₹5,000 -> HITL)
3. ORD_2003 -> AUTO_SUBMIT (Strong winnable defense, low value -> Contest)
4. ORD_2004 -> HUMAN_REVIEW (Ambiguous evidence, high value -> HITL Contest Review)
5. ORD_2005 -> ACCEPT_LOSS (Weak/no evidence, unmerited claim -> Accept Loss)
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List

from config.settings import settings
from features.dispute_webhook.models.payload_models import DisputeScenario

# ── 5 Core Gate-Decision Test Scenarios matching PostgreSQL Seed Data ─────────

SCENARIO_1_AUTO_REFUND = DisputeScenario(
    scenario_id="gate_1_auto_refund",
    name="Test 1: Auto Refund (ORD_2001 - Earbuds ₹2,999)",
    description="Genuinely lost in transit (Delhivery unfulfilled, customer notified early), low value <= ₹5,000 -> routes to AUTO_REFUND.",
    dispute_id_base="disp_2001",
    order_id="ORD_2001",
    payment_id="pay_XYZ2001",
    amount_inr=2999,
    reason_code="product_not_received",
    phase="chargeback",
    customer_email="priya.sharma@gmail.com",
    contact="+919876543210",
    item_description="Bluetooth Earbuds Pro",
    bank="HDFC",
)

SCENARIO_2_REFUND_REVIEW = DisputeScenario(
    scenario_id="gate_2_refund_review",
    name="Test 2: Refund Review HITL (ORD_2002 - iPad ₹24,999)",
    description="Genuinely lost in transit (BlueDart unfulfilled), high value > ₹5,000 -> routes to REFUND_REVIEW for human approval.",
    dispute_id_base="disp_2002",
    order_id="ORD_2002",
    payment_id="pay_XYZ2002",
    amount_inr=24999,
    reason_code="product_not_received",
    phase="chargeback",
    customer_email="rahul.mehta@gmail.com",
    contact="+919876543211",
    item_description="Apple iPad 9th Gen 64GB",
    bank="ICICI",
)

SCENARIO_3_AUTO_SUBMIT = DisputeScenario(
    scenario_id="gate_3_auto_submit",
    name="Test 3: Auto Submit Contest (ORD_2003 - Shoes ₹3,499)",
    description="Strong winnable defense (OTP delivered + customer confirmed fit in email), low value -> routes to AUTO_SUBMIT.",
    dispute_id_base="disp_2003",
    order_id="ORD_2003",
    payment_id="pay_XYZ2003",
    amount_inr=3499,
    reason_code="product_not_received",
    phase="chargeback",
    customer_email="friendly_fraud1@outlook.com",
    contact="+919876543212",
    item_description="Nike Running Shoes - Size 9",
    bank="SBI",
)

SCENARIO_4_HUMAN_REVIEW = DisputeScenario(
    scenario_id="gate_4_human_review",
    name="Test 4: Human Review Contest (ORD_2004 - Monitor ₹18,500)",
    description="Ambiguous evidence (Left at door without signature, no chat, high value) -> routes to HUMAN_REVIEW.",
    dispute_id_base="disp_2004",
    order_id="ORD_2004",
    payment_id="pay_XYZ2004",
    amount_inr=18500,
    reason_code="product_unacceptable",
    phase="chargeback",
    customer_email="ambiguous_case@yahoo.com",
    contact="+919876543213",
    item_description='Samsung 27" Monitor',
    bank="Axis",
)

SCENARIO_5_ACCEPT_LOSS = DisputeScenario(
    scenario_id="gate_5_accept_loss",
    name="Test 5: Accept Loss (ORD_2005 - Phone Case ₹1,299)",
    description="Weak defense, inconsistent buyer claim, high risk telemetry -> routes to ACCEPT_LOSS.",
    dispute_id_base="disp_2005",
    order_id="ORD_2005",
    payment_id="pay_XYZ2005",
    amount_inr=1299,
    reason_code="fraud",
    phase="fraud",
    customer_email="ghost_buyer@protonmail.com",
    contact="+919876543214",
    item_description="Phone Case - Clear",
    bank="Kotak",
)

ALL_SCENARIOS: List[DisputeScenario] = [
    SCENARIO_1_AUTO_REFUND,
    SCENARIO_2_REFUND_REVIEW,
    SCENARIO_3_AUTO_SUBMIT,
    SCENARIO_4_HUMAN_REVIEW,
    SCENARIO_5_ACCEPT_LOSS,
]


def build_dispute_webhook_payload(
    scenario: DisputeScenario,
    unique_suffix: bool | None = None,
) -> dict:
    """
    Constructs a valid Razorpay webhook JSON payload matching the target scenario.

    :param scenario: The DisputeScenario metadata
    :param unique_suffix: If True, appends timestamp/uuid to dispute_id
    :return: Formatted dictionary payload ready for HMAC-SHA256 signature & HTTP POST
    """
    should_uniquify = settings.UNIQUE_DISPUTE_IDS if unique_suffix is None else unique_suffix

    now_ts = int(time.time())
    
    if should_uniquify:
        short_id = uuid.uuid4().hex[:6]
        dispute_id = f"{scenario.dispute_id_base}_{short_id}"
    else:
        dispute_id = scenario.dispute_id_base

    return {
        "entity": "event",
        "account_id": scenario.account_id,
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": scenario.payment_id,
                    "entity": "payment",
                    "amount": scenario.amount_paise,
                    "currency": "INR",
                    "base_amount": scenario.amount_paise,
                    "status": "captured",
                    "order_id": scenario.order_id,
                    "invoice_id": None,
                    "international": False,
                    "method": scenario.method,
                    "amount_refunded": 0,
                    "amount_transferred": 0,
                    "refund_status": None,
                    "captured": True,
                    "description": scenario.item_description,
                    "card_id": scenario.card_id,
                    "bank": scenario.bank,
                    "wallet": None,
                    "vpa": None,
                    "email": scenario.customer_email,
                    "contact": scenario.contact,
                    "notes": [],
                    "fee": 0,
                    "tax": 0,
                    "error_code": None,
                    "error_description": None,
                    "error_source": None,
                    "error_step": None,
                    "error_reason": None,
                    "acquirer_data": {},
                    "created_at": now_ts - 86400 * 2,
                }
            },
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "entity": "dispute",
                    "payment_id": scenario.payment_id,
                    "amount": scenario.amount_paise,
                    "currency": "INR",
                    "amount_deducted": 0,
                    "reason_code": scenario.reason_code,
                    "respond_by": now_ts + 86400 * 5,
                    "status": "open",
                    "evidence": {
                        "amount": scenario.amount_paise,
                        "summary": None,
                        "shipping_proof": None,
                        "billing_proof": None,
                        "cancellation_proof": None,
                        "customer_communication": None,
                        "proof_of_service": None,
                        "explanation_letter": None,
                        "refund_confirmation": None,
                        "access_activity_log": None,
                        "refund_cancellation_policy": None,
                        "term_and_conditions": None,
                        "others": None,
                        "submitted_at": None,
                    },
                    "phase": scenario.phase,
                    "created_at": now_ts,
                }
            },
        },
        "created_at": now_ts,
    }
