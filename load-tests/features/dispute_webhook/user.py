"""
Locust HttpUser definitions for dispute webhook testing.
"""

from __future__ import annotations

from locust import HttpUser, constant

from config.settings import settings
from features.dispute_webhook.tasks import (
    DisputeRandomBatchTaskSet,
    DisputeSequentialTaskSet,
)


class DisputeSequentialUser(HttpUser):
    """
    User executing the 5 test scenarios sequentially with a 10-second delay between requests.
    Recommended for predictable, scenario-by-scenario verification.
    """

    tasks = [DisputeSequentialTaskSet]
    host = settings.TARGET_HOST
    wait_time = constant(settings.TASK_DELAY_SECONDS)


class DisputeWebhookUser(HttpUser):
    """
    User executing concurrent/random dispute webhook requests across all 5 scenarios
    with a 10-second delay between requests per user.
    """

    tasks = [DisputeRandomBatchTaskSet]
    host = settings.TARGET_HOST
    wait_time = constant(settings.TASK_DELAY_SECONDS)
