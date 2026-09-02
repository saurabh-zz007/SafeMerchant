"""
Chaos-testing script: run_test_batch.py

Blasts mock dispute webhook JSONs at the /webhook endpoint concurrently.
Measures precision, recall, false-positive financial costs, and throughput.
Includes HMAC-SHA256 signature verification matching Razorpay's production specification.

Usage:
    python -m tests.run_test_batch --url http://localhost:8000/api/v1/webhook --count 100
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


# Webhook secret for signing test payloads
WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE")

# ── Dispute Archetypes for Mock Generation ──

REASON_CODES = ["chargeback", "fraud", "product_not_received", "processed_invalid_expired_card", "duplicate"]
PHASES = ["chargeback", "pre_arbitration"]

# Known payment IDs
KNOWN_ORDER_IDS = {
    "pay_EFtmUsbwpXwBHI": {"amount": 52976, "expected_action": "human_review"},
    "pay_XYZ1001": {"amount": 52976, "expected_action": "human_review"},
    "pay_XYZ1002": {"amount": 15000, "expected_action": "human_review"},
    "pay_XYZ1003": {"amount": 4500,  "expected_action": "human_review"},
}

# Unknown payment IDs (should produce "no evidence" → accept_loss)
UNKNOWN_PAYMENT_IDS = [f"pay_FAKE_{i:04d}" for i in range(50)]


@dataclass
class TestResult:
    dispute_id: str
    payment_id: str
    expected_action: str
    actual_action: str | None = None
    winnability_score: float | None = None
    latency_ms: float = 0.0
    error: str | None = None
    success: bool = False


@dataclass
class BatchReport:
    total: int = 0
    successes: int = 0
    failures: int = 0
    results: list[TestResult] = field(default_factory=list)

    # Classification metrics
    true_positives: int = 0   # Correctly contested
    true_negatives: int = 0   # Correctly accepted loss
    false_positives: int = 0  # Incorrectly contested (financial risk!)
    false_negatives: int = 0  # Incorrectly accepted loss

    # Financial
    false_positive_cost_inr: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        latencies = [r.latency_ms for r in self.results if r.success]
        return sum(latencies) / len(latencies) if latencies else 0.0


def generate_mock_dispute(index: int) -> tuple[dict, str]:
    """
    Generate a mock dispute webhook payload matching Razorpay's real payload structure.
    Returns (payload_dict, expected_gate_action).
    """
    if random.random() < 0.6:
        payment_id = random.choice(list(KNOWN_ORDER_IDS.keys()))
        amount_inr = KNOWN_ORDER_IDS[payment_id]["amount"]
        expected = KNOWN_ORDER_IDS[payment_id]["expected_action"]
    else:
        payment_id = random.choice(UNKNOWN_PAYMENT_IDS)
        amount_inr = random.randint(500, 50000)
        expected = "accept_loss"

    amount_paise = amount_inr * 100
    now_ts = int(time.time())

    payload = {
        "entity": "event",
        "account_id": "acc_CFvOKjkTwf3GQy",
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount_paise,
                    "currency": "INR",
                    "base_amount": amount_paise,
                    "status": "captured",
                    "order_id": f"order_{payment_id.replace('pay_', '')}",
                    "invoice_id": None,
                    "international": False,
                    "method": "card",
                    "amount_refunded": 0,
                    "amount_transferred": 0,
                    "refund_status": None,
                    "captured": True,
                    "description": None,
                    "card_id": "card_EADblPSDnnk5ZG",
                    "bank": "HDFC",
                    "wallet": None,
                    "vpa": None,
                    "email": "gaurav.kumar@example.com",
                    "contact": "+919900000000",
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
                    "id": f"disp_TEST_{index:04d}",
                    "entity": "dispute",
                    "payment_id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "amount_deducted": 0,
                    "reason_code": random.choice(REASON_CODES),
                    "respond_by": now_ts + 86400 * 5,
                    "status": "open",
                    "evidence": {
                        "amount": amount_paise,
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
                    "phase": random.choice(PHASES),
                    "created_at": now_ts,
                }
            }
        },
        "created_at": now_ts
    }

    return payload, expected


async def send_dispute(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    expected_action: str,
    dispute_id: str,
    secret: str = WEBHOOK_SECRET,
) -> TestResult:
    """Send a single dispute webhook with HMAC-SHA256 signature and record the result."""
    payment_id = payload["payload"]["payment"]["entity"]["id"]
    result = TestResult(
        dispute_id=dispute_id,
        payment_id=payment_id,
        expected_action=expected_action,
    )

    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sig,
    }

    start = time.perf_counter()
    try:
        response = await client.post(url, content=raw_body, headers=headers, timeout=30.0)
        result.latency_ms = (time.perf_counter() - start) * 1000

        if response.status_code in (200, 202):
            data = response.json()
            result.actual_action = data.get("gate_action")
            result.winnability_score = data.get("winnability_score")
            result.success = True
        else:
            result.error = f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        result.latency_ms = (time.perf_counter() - start) * 1000
        result.error = str(e)

    return result


async def run_batch(url: str, count: int, concurrency: int = 20) -> BatchReport:
    """Run the chaos test batch."""
    report = BatchReport(total=count)

    # Generate all mock disputes
    tasks_data = []
    for i in range(count):
        payload, expected = generate_mock_dispute(i)
        dispute_id = payload["payload"]["dispute"]["entity"]["id"]
        tasks_data.append((payload, expected, dispute_id))

    # Execute with bounded concurrency
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_send(client, payload, expected, dispute_id):
        async with semaphore:
            return await send_dispute(client, url, payload, expected, dispute_id)

    async with httpx.AsyncClient() as client:
        tasks = [
            bounded_send(client, payload, expected, dispute_id)
            for payload, expected, dispute_id in tasks_data
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Analyze results
    for r in results:
        if isinstance(r, Exception):
            report.failures += 1
            continue

        report.results.append(r)
        if r.success:
            report.successes += 1

            # Classification
            is_contest = r.actual_action in ("auto_submit", "human_review")
            expected_contest = r.expected_action in ("auto_submit", "human_review")

            if is_contest and expected_contest:
                report.true_positives += 1
            elif not is_contest and not expected_contest:
                report.true_negatives += 1
            elif is_contest and not expected_contest:
                report.false_positives += 1
                report.false_positive_cost_inr += r.winnability_score or 0
            elif not is_contest and expected_contest:
                report.false_negatives += 1
        else:
            report.failures += 1

    return report


def print_report(report: BatchReport):
    """Print a formatted chaos test report."""
    print("\n" + "=" * 60)
    print("  CHAOS TEST REPORT — SafeMerchant Risk Agent")
    print("=" * 60)
    print(f"  Total disputes:     {report.total}")
    print(f"  Successes:          {report.successes}")
    print(f"  Failures:           {report.failures}")
    print(f"  Avg latency:        {report.avg_latency_ms:.1f} ms")
    print("-" * 60)
    print(f"  True positives:     {report.true_positives}")
    print(f"  True negatives:     {report.true_negatives}")
    print(f"  False positives:    {report.false_positives}  ⚠️  (financial risk)")
    print(f"  False negatives:    {report.false_negatives}")
    print("-" * 60)
    print(f"  Precision:          {report.precision:.2%}")
    print(f"  Recall:             {report.recall:.2%}")
    print(f"  FP cost (INR):      ₹{report.false_positive_cost_inr:,}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SafeMerchant Chaos Test")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/webhook")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    print(f"🔥 Blasting {args.count} disputes at {args.url} (concurrency={args.concurrency})")
    report = asyncio.run(run_batch(args.url, args.count, args.concurrency))
    print_report(report)
