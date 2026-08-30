"""
Chaos-testing script: run_test_batch.py

Blasts 100 mock dispute webhook JSONs at the /webhook endpoint concurrently.
Measures precision, recall, false-positive financial costs, and throughput.

Usage:
    python -m tests.run_test_batch --url http://localhost:8000/api/v1/webhook --count 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


# ── Dispute Archetypes for Mock Generation ──

REASON_CODES = ["chargeback", "fraud", "product_not_received", "duplicate", "other"]
PHASES = ["chargeback", "pre_arbitration"]

# Known order IDs from seed data (should produce valid evidence)
KNOWN_ORDER_IDS = {
    "pay_XYZ1001": {"amount": 52976, "expected_action": "human_review"},   # High amount, delivered
    "pay_XYZ1002": {"amount": 15000, "expected_action": "human_review"},   # No shipping, has 2FA
    "pay_XYZ1003": {"amount": 4500,  "expected_action": "human_review"},   # In transit, low amount
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
    Generate a mock dispute webhook payload.
    Returns (payload_dict, expected_gate_action).
    """
    # 60% known orders (should have evidence), 40% unknown (no evidence → accept_loss)
    if random.random() < 0.6:
        payment_id = random.choice(list(KNOWN_ORDER_IDS.keys()))
        amount = KNOWN_ORDER_IDS[payment_id]["amount"]
        expected = KNOWN_ORDER_IDS[payment_id]["expected_action"]
    else:
        payment_id = random.choice(UNKNOWN_PAYMENT_IDS)
        amount = random.randint(500, 50000)
        expected = "accept_loss"

    payload = {
        "event": "payment.dispute.created",
        "payload": {
            "entity": {
                "id": f"disp_TEST_{index:04d}",
                "payment_id": payment_id,
                "amount": amount,
                "currency": "INR",
                "reason_code": random.choice(REASON_CODES),
                "phase": random.choice(PHASES),
                "status": "open",
            }
        },
    }

    return payload, expected


async def send_dispute(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    expected_action: str,
    dispute_id: str,
) -> TestResult:
    """Send a single dispute webhook and record the result."""
    result = TestResult(
        dispute_id=dispute_id,
        payment_id=payload["payload"]["entity"]["payment_id"],
        expected_action=expected_action,
    )

    start = time.perf_counter()
    try:
        response = await client.post(url, json=payload, timeout=30.0)
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
        dispute_id = payload["payload"]["entity"]["id"]
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
