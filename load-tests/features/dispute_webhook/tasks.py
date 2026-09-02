"""
Locust TaskSets for executing dispute webhook load test scenarios.
Includes sequential execution with a 10-second delay between each gate-decision scenario.
"""

from __future__ import annotations

import logging
from locust import SequentialTaskSet, TaskSet, constant, task

from config.settings import settings
from core.webhook_client import SignedWebhookClient
from features.dispute_webhook.data.test_payloads import (
    ALL_SCENARIOS,
    SCENARIO_1_AUTO_REFUND,
    SCENARIO_2_REFUND_REVIEW,
    SCENARIO_3_AUTO_SUBMIT,
    SCENARIO_4_HUMAN_REVIEW,
    SCENARIO_5_ACCEPT_LOSS,
    build_dispute_webhook_payload,
)

logger = logging.getLogger(__name__)


class DisputeSequentialTaskSet(SequentialTaskSet):
    """
    Executes the 5 Gate-Decision scenarios sequentially in order with a 10-second delay:
    1. ORD_2001 -> AUTO_REFUND (Earbuds ₹2,999)
       ↓ (10s delay)
    2. ORD_2002 -> REFUND_REVIEW / HITL (iPad ₹24,999)
       ↓ (10s delay)
    3. ORD_2003 -> AUTO_SUBMIT / Contest (Shoes ₹3,499)
       ↓ (10s delay)
    4. ORD_2004 -> HUMAN_REVIEW / Contest (Monitor ₹18,500)
       ↓ (10s delay)
    5. ORD_2005 -> ACCEPT_LOSS (Phone Case ₹1,299)
    """

    # Enforce 10-second delay between task executions
    wait_time = constant(settings.TASK_DELAY_SECONDS)

    @task
    def test_1_gate_auto_refund(self):
        """Test 1: Hit webhook with ORD_2001 (Should route to AUTO_REFUND)."""
        payload = build_dispute_webhook_payload(SCENARIO_1_AUTO_REFUND)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="1_Gate_AutoRefund_ORD2001",
        )

    @task
    def test_2_gate_refund_review(self):
        """Test 2: Hit webhook with ORD_2002 (Should route to REFUND_REVIEW / HITL)."""
        payload = build_dispute_webhook_payload(SCENARIO_2_REFUND_REVIEW)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="2_Gate_RefundReview_ORD2002",
        )

    @task
    def test_3_gate_auto_submit(self):
        """Test 3: Hit webhook with ORD_2003 (Should route to AUTO_SUBMIT / Contest)."""
        payload = build_dispute_webhook_payload(SCENARIO_3_AUTO_SUBMIT)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="3_Gate_AutoSubmit_ORD2003",
        )

    @task
    def test_4_gate_human_review(self):
        """Test 4: Hit webhook with ORD_2004 (Should route to HUMAN_REVIEW / Contest)."""
        payload = build_dispute_webhook_payload(SCENARIO_4_HUMAN_REVIEW)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="4_Gate_HumanReview_ORD2004",
        )

    @task
    def test_5_gate_accept_loss(self):
        """Test 5: Hit webhook with ORD_2005 (Should route to ACCEPT_LOSS)."""
        payload = build_dispute_webhook_payload(SCENARIO_5_ACCEPT_LOSS)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="5_Gate_AcceptLoss_ORD2005",
        )


class DisputeRandomBatchTaskSet(TaskSet):
    """
    Randomized or weighted load test task set across all 5 Gate-Decision scenarios.
    Each user waits 10 seconds between requests.
    """

    wait_time = constant(settings.TASK_DELAY_SECONDS)

    @task(3)
    def send_auto_refund_dispute(self):
        payload = build_dispute_webhook_payload(SCENARIO_1_AUTO_REFUND)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="Random_Gate_AutoRefund_ORD2001",
        )

    @task(2)
    def send_refund_review_dispute(self):
        payload = build_dispute_webhook_payload(SCENARIO_2_REFUND_REVIEW)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="Random_Gate_RefundReview_ORD2002",
        )

    @task(3)
    def send_auto_submit_dispute(self):
        payload = build_dispute_webhook_payload(SCENARIO_3_AUTO_SUBMIT)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="Random_Gate_AutoSubmit_ORD2003",
        )

    @task(2)
    def send_human_review_dispute(self):
        payload = build_dispute_webhook_payload(SCENARIO_4_HUMAN_REVIEW)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="Random_Gate_HumanReview_ORD2004",
        )

    @task(1)
    def send_accept_loss_dispute(self):
        payload = build_dispute_webhook_payload(SCENARIO_5_ACCEPT_LOSS)
        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name="Random_Gate_AcceptLoss_ORD2005",
        )
