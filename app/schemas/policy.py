"""Trusted refund policy models."""

from pydantic import BaseModel, ConfigDict


class RefundPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    refund_window_days: int
    auto_approval_limit: int


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    approval_required: bool
    days_since_purchase: int
