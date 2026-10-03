"""Workflow state values and deterministic transition validation."""

from enum import Enum

from app.exceptions import InvalidStateTransitionError


class AgentState(str, Enum):
    STARTED = "STARTED"
    INTENT_UNDERSTOOD = "INTENT_UNDERSTOOD"
    PLANNED = "PLANNED"
    POLICY_CHECKED = "POLICY_CHECKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REFUND_READY = "REFUND_READY"
    REFUND_EXECUTING = "REFUND_EXECUTING"
    REFUND_OUTCOME_UNKNOWN = "REFUND_OUTCOME_UNKNOWN"
    REFUND_VERIFIED = "REFUND_VERIFIED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    COMPLETE = "COMPLETE"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RefundStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.STARTED: frozenset({AgentState.INTENT_UNDERSTOOD}),
    AgentState.INTENT_UNDERSTOOD: frozenset({AgentState.PLANNED}),
    AgentState.PLANNED: frozenset({AgentState.POLICY_CHECKED}),
    AgentState.POLICY_CHECKED: frozenset(
        {
            AgentState.WAITING_APPROVAL,
            AgentState.REFUND_READY,
            AgentState.NEEDS_HUMAN_REVIEW,
        }
    ),
    AgentState.WAITING_APPROVAL: frozenset(
        {AgentState.REFUND_READY, AgentState.NEEDS_HUMAN_REVIEW}
    ),
    AgentState.REFUND_READY: frozenset({AgentState.REFUND_EXECUTING}),
    AgentState.REFUND_EXECUTING: frozenset(
        {AgentState.REFUND_OUTCOME_UNKNOWN, AgentState.REFUND_VERIFIED}
    ),
    AgentState.REFUND_OUTCOME_UNKNOWN: frozenset(
        {AgentState.REFUND_VERIFIED, AgentState.NEEDS_HUMAN_REVIEW}
    ),
    AgentState.REFUND_VERIFIED: frozenset({AgentState.COMPLETE}),
}


def validate_state_transition(current_state: AgentState, new_state: AgentState) -> None:
    """Reject state changes not explicitly authorized by the workflow."""
    if new_state not in ALLOWED_TRANSITIONS.get(current_state, frozenset()):
        raise InvalidStateTransitionError(
            f"Cannot transition agent run from {current_state.value} "
            f"to {new_state.value}."
        )
