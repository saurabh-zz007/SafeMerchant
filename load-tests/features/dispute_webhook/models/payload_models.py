"""
Domain models and dataclasses for dispute test scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DisputeScenario:
    """Represents a specific dispute test scenario matching merchant records."""

    scenario_id: str
    name: str
    description: str
    dispute_id_base: str
    order_id: str
    payment_id: str
    amount_inr: int
    reason_code: str
    phase: str
    customer_email: str
    contact: str
    item_description: str
    card_id: str = "card_EADblPSDnnk5ZG"
    bank: str = "HDFC"
    method: str = "card"
    account_id: str = "acc_CFvOKjkTwf3GQy"

    @property
    def amount_paise(self) -> int:
        """Returns the amount converted to paise."""
        return self.amount_inr * 100
