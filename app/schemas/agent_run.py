"""Durable agent workflow model."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.states import AgentState, ApprovalStatus


class AgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ticket_id: str
    order_id: str | None = None
    intent: str | None = None
    current_state: AgentState
    policy_passed: bool | None = None
    approval_status: ApprovalStatus | None = None
    refund_id: str | None = None
    idempotency_key: str | None = None
    last_observation: str | None = None
    created_at: datetime
    updated_at: datetime
