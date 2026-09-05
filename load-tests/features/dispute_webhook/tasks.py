"""
Locust TaskSets for executing dispute webhook load test scenarios.
Dynamically executes test case payloads loaded from load-tests/testcase.json.
Enforces a 10-second delay between each scenario execution.
"""

from __future__ import annotations

import logging
import random
from locust import TaskSet, constant, task

from config.settings import settings
from core.webhook_client import SignedWebhookClient
from features.dispute_webhook.data.test_payloads import (
    load_testcase_payloads,
    prepare_testcase_for_request,
)

logger = logging.getLogger(__name__)


class DisputeSequentialTaskSet(TaskSet):
    """
    Sequentially executes each test case from load-tests/testcase.json in order,
    pacing requests with a 10-second delay (settings.TASK_DELAY_SECONDS).

    Each test case is reported under its own descriptive label in Locust statistics
    (e.g., '1_ORD_2006_product_not_received_INR_2499').
    """

    wait_time = constant(settings.TASK_DELAY_SECONDS)

    def on_start(self):
        super().on_start()
        self._current_index = 0

    @task
    def execute_next_dispute_scenario(self):
        """Dispatches the next sequential test case from testcase.json."""
        payloads = load_testcase_payloads()
        if not payloads:
            logger.error("No test cases found to execute in testcase.json.")
            return

        total_cases = len(payloads)
        idx = self._current_index % total_cases
        self._current_index += 1

        payload, request_label = prepare_testcase_for_request(
            raw_item=payloads[idx],
            index=idx,
        )

        logger.info(
            "Firing dispute webhook [%d/%d]: %s",
            idx + 1,
            total_cases,
            request_label,
        )

        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name=request_label,
        )


class DisputeRandomBatchTaskSet(TaskSet):
    """
    Randomized load test task set selecting from testcase.json.
    Each user waits settings.TASK_DELAY_SECONDS between requests.
    """

    wait_time = constant(settings.TASK_DELAY_SECONDS)

    @task
    def execute_random_dispute_scenario(self):
        """Picks a random test case from testcase.json and posts it."""
        payloads = load_testcase_payloads()
        if not payloads:
            logger.error("No test cases found in testcase.json.")
            return

        idx = random.randrange(len(payloads))
        payload, request_label = prepare_testcase_for_request(
            raw_item=payloads[idx],
            index=idx,
        )

        SignedWebhookClient.post_dispute_webhook(
            client=self.client,
            payload=payload,
            name=f"Random_{request_label}",
        )
