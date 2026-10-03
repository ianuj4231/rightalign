"""Structured LLM response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class IntentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["REFUND_REQUEST", "UNKNOWN"]
    reason: str | None = None
    customer_claims_prior_approval: bool = False
