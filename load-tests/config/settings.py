"""
Configuration settings for SafeMerchant Locust load tests.
Supports environment variables and .env file loading.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Try loading .env from load-tests directory, or fallback to backend/.env
LOAD_TESTS_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = LOAD_TESTS_DIR.parent
BACKEND_ENV = WORKSPACE_ROOT / "backend" / ".env"
LOCAL_ENV = LOAD_TESTS_DIR / ".env"

if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV)
elif BACKEND_ENV.exists():
    load_dotenv(BACKEND_ENV)
else:
    load_dotenv()


class Settings:
    """Load test runtime configuration."""

    # Target Backend API Server
    TARGET_HOST: str = os.getenv("TARGET_HOST", "http://localhost:8000").rstrip("/")
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/api/v1/webhook")

    # Razorpay Webhook Secret for HMAC-SHA256 signature verification
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv(
        "RAZORPAY_WEBHOOK_SECRET",
        "whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE",
    )

    # Delay between consecutive tests in seconds (default 10.0 seconds as required)
    TASK_DELAY_SECONDS: float = float(os.getenv("TASK_DELAY_SECONDS", "10.0"))

    # Whether to append unique timestamp suffixes to dispute IDs (False by default to test real dispute ID idempotency)
    UNIQUE_DISPUTE_IDS: bool = os.getenv("UNIQUE_DISPUTE_IDS", "false").lower() in ("true", "1", "yes")

    # Request timeout in seconds
    REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "30.0"))


settings = Settings()
