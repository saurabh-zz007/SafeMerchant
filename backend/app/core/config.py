"""
Application configuration via Pydantic Settings.

Reads from .env file or environment variables.
All thresholds for the defense-only gate are configured here.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for the SafeMerchant backend."""

    # ── Database ──
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/safemerchant",
        description="Async SQLAlchemy connection string for PostgreSQL",
    )

    # ── LLM Provider (OpenRouter) ──
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for triage and drafting LLM calls",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL (OpenAI-compatible)",
    )
    openrouter_model_name: str = Field(
        default="openai/gpt-4o",
        description="Model name on OpenRouter (e.g., openai/gpt-4o, google/gemini-pro)",
    )

    # ── Razorpay API (for Refunds) ──
    razorpay_key_id: str = Field(
        default="",
        description="Razorpay API Key ID for refund operations",
    )
    razorpay_key_secret: str = Field(
        default="",
        description="Razorpay API Key Secret for refund operations",
    )

    # ── Agent Gate Thresholds (Defense-Only) ──
    auto_submit_score_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum winnability score to auto-submit without human review",
    )
    auto_submit_amount_ceiling_inr: int = Field(
        default=10_000,
        ge=0,
        description="Maximum dispute amount (INR) for auto-submission",
    )
    auto_refund_amount_ceiling_inr: int = Field(
        default=10_000,
        ge=0,
        description="Maximum dispute amount (INR) for auto-refund without human review",
    )

    # ── Metrics ──
    sla_breach_threshold_hours: int = Field(
        default=24,
        ge=1,
        description="Hours after which an action_required dispute is flagged as SLA-breached",
    )

    # ── Server ──
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=True)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance — import this across the app
settings = Settings()
