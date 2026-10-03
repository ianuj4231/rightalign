"""Trusted order models."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict


class OrderRefundStatus(str, Enum):
    NONE = "NONE"
    REFUNDED = "REFUNDED"


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    amount: int
    purchase_date: date
    status: str
    refund_status: OrderRefundStatus
