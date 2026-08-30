"""
Synthetic dispute generator for batch evaluation.

Generates ~50 dispute scenarios across 5 archetypes with known ground truth:
1. Clear Win      — delivered, signed, 2FA, comms show product usage
2. Clear Loss     — no shipping, no delivery, no comms
3. Legitimate Cust — no delivery + pre-existing complaint → refund
4. Ambiguous       — mixed evidence, high amount → human_review
5. Fraud Indicators — 2FA verified, suspicious signals → contest

Each dispute is a dict with:
  - webhook_payload: valid DisputeWebhookEvent JSON
  - evidence_bundle: the evidence the DB would return
  - ground_truth: expected gate_action / recommended_action
  - ground_truth_category: descriptive label
"""

from __future__ import annotations

import random
from typing import Any

random.seed(42)  # Reproducible evaluation


def _make_webhook(
    dispute_id: str,
    payment_id: str,
    order_id: str,
    amount: int,
    reason_code: str = "chargeback",
    phase: str = "chargeback",
    email: str = "customer@test.com",
    created_at: int | None = 1787313600,  # 2026-08-20 00:00:00 UTC
) -> dict:
    """Build a valid DisputeWebhookEvent payload."""
    return {
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": order_id,
                    "email": email,
                }
            },
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                    "reason_code": reason_code,
                    "phase": phase,
                    "status": "open",
                    "created_at": created_at,
                }
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════
# ARCHETYPE 1: CLEAR WIN (expect: contest → auto_submit)
# ═══════════════════════════════════════════════════════════════════

def _clear_win_disputes() -> list[dict[str, Any]]:
    """Generate clear-win disputes — strong merchant evidence."""
    disputes = []
    for i in range(1, 11):
        order_id = f"ORD_CW_{i:03d}"
        payment_id = f"pay_CW_{i:03d}"
        dispute_id = f"disp_CW_{i:03d}"
        amount = random.randint(1000, 8000)

        disputes.append({
            "webhook_payload": _make_webhook(
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                amount=amount,
                reason_code=random.choice(["chargeback", "product_not_received"]),
            ),
            "evidence_bundle": {
                "order": {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "customer_email": f"customer_{i}@test.com",
                    "amount_inr": amount,
                    "item_description": f"Product {i} - Clear Win",
                    "created_at": "2026-08-10T14:00:00+00:00",
                },
                "shipping": {
                    "tracking_id": f"TRK_CW_{i:03d}",
                    "courier_partner": random.choice(["Delhivery", "BlueDart", "DTDC"]),
                    "delivery_status": "Delivered",
                    "signed_by": "Self (OTP Verified)",
                    "delivery_timestamp": "2026-08-13T16:45:00+00:00",
                },
                "communications": [
                    {
                        "ticket_id": f"TCK_CW_{i:03d}",
                        "channel": "Email",
                        "message_transcript": (
                            "Customer: How do I set up this product? "
                            "Support: Please follow the instructions in the box."
                        ),
                        "logged_at": "2026-08-14T10:00:00+00:00",
                    }
                ],
                "risk_signals": {
                    "ip_address": "203.0.113.1",
                    "device_fingerprint": "Chrome Desktop",
                    "is_2fa_verified": True,
                    "account_age_days": random.randint(200, 1000),
                },
            },
            "ground_truth": "auto_submit",
            "ground_truth_category": "contest_win",
        })
    return disputes


# ═══════════════════════════════════════════════════════════════════
# ARCHETYPE 2: CLEAR LOSS (expect: accept_loss)
# ═══════════════════════════════════════════════════════════════════

def _clear_loss_disputes() -> list[dict[str, Any]]:
    """Generate clear-loss disputes — no evidence at all."""
    disputes = []
    for i in range(1, 11):
        order_id = f"ORD_CL_{i:03d}"
        payment_id = f"pay_CL_{i:03d}"
        dispute_id = f"disp_CL_{i:03d}"
        amount = random.randint(2000, 15000)

        disputes.append({
            "webhook_payload": _make_webhook(
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                amount=amount,
                reason_code="chargeback",
            ),
            "evidence_bundle": {
                "order": {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "customer_email": f"unknown_{i}@test.com",
                    "amount_inr": amount,
                    "item_description": f"Product {i} - Clear Loss",
                    "created_at": "2026-08-10T14:00:00+00:00",
                },
                "shipping": None,
                "communications": [],
                "risk_signals": None,
            },
            "ground_truth": "accept_loss",
            "ground_truth_category": "contest_loss",
        })
    return disputes


# ═══════════════════════════════════════════════════════════════════
# ARCHETYPE 3: LEGITIMATE CUSTOMER (expect: refund)
# ═══════════════════════════════════════════════════════════════════

def _legitimate_customer_disputes() -> list[dict[str, Any]]:
    """Generate legitimate customer disputes — no delivery + pre-existing complaint."""
    disputes = []
    for i in range(1, 11):
        order_id = f"ORD_LC_{i:03d}"
        payment_id = f"pay_LC_{i:03d}"
        dispute_id = f"disp_LC_{i:03d}"
        amount = random.randint(1000, 6000)

        disputes.append({
            "webhook_payload": _make_webhook(
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                amount=amount,
                reason_code="product_not_received",
                # Dispute created on Aug 20, 2026
                created_at=1787313600,
            ),
            "evidence_bundle": {
                "order": {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "customer_email": f"buyer_{i}@test.com",
                    "amount_inr": amount,
                    "item_description": f"Product {i} - Legitimate Customer",
                    "created_at": "2026-08-10T14:00:00+00:00",
                },
                "shipping": {
                    "tracking_id": f"TRK_LC_{i:03d}",
                    "courier_partner": "BlueDart",
                    "delivery_status": "In_Transit",
                    "signed_by": None,
                    "delivery_timestamp": None,
                },
                "communications": [
                    {
                        "ticket_id": f"TCK_LC_{i:03d}",
                        "channel": "WhatsApp",
                        "message_transcript": (
                            "Customer: I haven't received my order yet. It's been 5 days. "
                            "Support: We're looking into it. "
                            "Customer: Please refund me, I need the money."
                        ),
                        # Complaint BEFORE dispute was filed
                        "logged_at": "2026-08-18T12:00:00+00:00",
                    }
                ],
                "risk_signals": None,
            },
            "ground_truth": "auto_refund",
            "ground_truth_category": "refund",
        })
    return disputes


# ═══════════════════════════════════════════════════════════════════
# ARCHETYPE 4: AMBIGUOUS / HIGH-VALUE (expect: human_review)
# ═══════════════════════════════════════════════════════════════════

def _ambiguous_disputes() -> list[dict[str, Any]]:
    """Generate ambiguous disputes — mixed evidence, high amounts."""
    disputes = []
    for i in range(1, 11):
        order_id = f"ORD_AM_{i:03d}"
        payment_id = f"pay_AM_{i:03d}"
        dispute_id = f"disp_AM_{i:03d}"
        # High amounts → should trigger human review
        amount = random.randint(15000, 50000)

        disputes.append({
            "webhook_payload": _make_webhook(
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                amount=amount,
                reason_code="product_not_as_described",
            ),
            "evidence_bundle": {
                "order": {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "customer_email": f"vip_{i}@test.com",
                    "amount_inr": amount,
                    "item_description": f"Premium Product {i} - Ambiguous",
                    "created_at": "2026-08-10T14:00:00+00:00",
                },
                "shipping": {
                    "tracking_id": f"TRK_AM_{i:03d}",
                    "courier_partner": "Delhivery",
                    "delivery_status": "Delivered",
                    "signed_by": None,  # No signature
                    "delivery_timestamp": "2026-08-13T16:45:00+00:00",
                },
                "communications": [
                    {
                        "ticket_id": f"TCK_AM_{i:03d}",
                        "channel": "Email",
                        "message_transcript": (
                            "Customer: The product doesn't match the description. "
                            "Support: Can you share photos? "
                            "Customer: I'll send them later."
                        ),
                        "logged_at": "2026-08-15T10:00:00+00:00",
                    }
                ],
                "risk_signals": {
                    "ip_address": "203.0.113.50",
                    "device_fingerprint": "Safari Mobile",
                    "is_2fa_verified": False,
                    "account_age_days": random.randint(30, 100),
                },
            },
            "ground_truth": "human_review",
            "ground_truth_category": "human_review",
        })
    return disputes


# ═══════════════════════════════════════════════════════════════════
# ARCHETYPE 5: FRAUD INDICATORS (expect: contest)
# ═══════════════════════════════════════════════════════════════════

def _fraud_indicator_disputes() -> list[dict[str, Any]]:
    """Generate fraud-indicator disputes — verified identity, strong signals."""
    disputes = []
    for i in range(1, 11):
        order_id = f"ORD_FI_{i:03d}"
        payment_id = f"pay_FI_{i:03d}"
        dispute_id = f"disp_FI_{i:03d}"
        amount = random.randint(3000, 9000)

        disputes.append({
            "webhook_payload": _make_webhook(
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                amount=amount,
                reason_code="fraud",
            ),
            "evidence_bundle": {
                "order": {
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "customer_email": f"suspicious_{i}@test.com",
                    "amount_inr": amount,
                    "item_description": f"Digital Product {i} - Fraud Indicator",
                    "created_at": "2026-08-10T14:00:00+00:00",
                },
                "shipping": {
                    "tracking_id": f"TRK_FI_{i:03d}",
                    "courier_partner": "DTDC",
                    "delivery_status": "Delivered",
                    "signed_by": "Verified via OTP",
                    "delivery_timestamp": "2026-08-12T10:00:00+00:00",
                },
                "communications": [
                    {
                        "ticket_id": f"TCK_FI_{i:03d}",
                        "channel": "Email",
                        "message_transcript": (
                            "Customer: Thanks for the quick delivery! "
                            "The product works great."
                        ),
                        "logged_at": "2026-08-13T08:00:00+00:00",
                    }
                ],
                "risk_signals": {
                    "ip_address": f"49.36.{random.randint(1,255)}.{random.randint(1,255)}",
                    "device_fingerprint": "iPhone 14 Pro - Safari",
                    "is_2fa_verified": True,
                    "account_age_days": random.randint(300, 800),
                },
            },
            "ground_truth": "auto_submit",
            "ground_truth_category": "contest_win",
        })
    return disputes


# ═══════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_synthetic_disputes() -> list[dict[str, Any]]:
    """
    Generate the full synthetic dispute dataset (~50 disputes).

    Returns a list of dicts, each with:
      - webhook_payload
      - evidence_bundle
      - ground_truth
      - ground_truth_category
    """
    disputes = []
    disputes.extend(_clear_win_disputes())
    disputes.extend(_clear_loss_disputes())
    disputes.extend(_legitimate_customer_disputes())
    disputes.extend(_ambiguous_disputes())
    disputes.extend(_fraud_indicator_disputes())

    # Shuffle for realistic evaluation order
    random.shuffle(disputes)
    return disputes


if __name__ == "__main__":
    disputes = generate_synthetic_disputes()
    print(f"Generated {len(disputes)} synthetic disputes")
    for cat in ["contest_win", "contest_loss", "refund", "human_review"]:
        count = sum(1 for d in disputes if d["ground_truth_category"] == cat)
        print(f"  {cat}: {count}")
