"""Customer support ticket models."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    order_id: str
    message: str
    status: TicketStatus
