"""
Main Locust entrypoint for SafeMerchant Load Tests.

Feature-First Architecture:
- Configuration: config/settings.py
- Security & Signer: core/security.py
- Webhook Client: core/webhook_client.py
- Dispute Webhook Feature: features/dispute_webhook/

Usage:
  1. Web UI Mode:
     locust -f load-tests/locustfile.py

  2. Headless Mode (Run 1 user through the 5 scenarios with 10s delay):
     locust -f load-tests/locustfile.py --headless -u 1 -r 1 -t 60s --host http://localhost:8000

  3. Concurrent Load Mode (10 users, each pacing with 10s delay):
     locust -f load-tests/locustfile.py --headless -u 10 -r 2 -t 2m --host http://localhost:8000
"""

import os
import sys
from pathlib import Path

# Ensure root load-tests folder and workspace are in Python path
CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from features.dispute_webhook.user import (
    DisputeSequentialUser,
    DisputeWebhookUser,
)

# Export user classes for Locust discovery
__all__ = ["DisputeSequentialUser", "DisputeWebhookUser"]
