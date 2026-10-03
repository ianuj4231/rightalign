"""Local refund and mock gateway models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.states import RefundStatus


class Refund(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    order_id: str
    amount: int
    idempotency_key: str
    gateway_transaction_id: str | None = None
    status: RefundStatus
    created_at: datetime
    updated_at: datetime


class GatewayRefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    amount: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1)


class GatewayRefundResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    idempotency_key: str
    order_id: str
    amount: int
    status: Literal["SUCCESS"]
    created_at: datetime
