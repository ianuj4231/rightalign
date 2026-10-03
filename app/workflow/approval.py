"""Trusted human approval commands."""

import logging

from app.database.agent_runs import record_approval_decision
from app.database.connection import database_transaction, get_database_connection
from app.states import AgentState, ApprovalStatus

logger = logging.getLogger(__name__)


def approve_refund(run_id: str) -> None:
    with get_database_connection() as connection, database_transaction(connection):
        record_approval_decision(
            connection,
            run_id=run_id,
            approval_status=ApprovalStatus.APPROVED,
            new_state=AgentState.REFUND_READY,
        )
    logger.info(
        "Trusted approval committed: run_id=%s decision=%s to_state=%s",
        run_id,
        ApprovalStatus.APPROVED.value,
        AgentState.REFUND_READY.value,
    )
    print("[APPROVAL]")
    print("APPROVED")


def reject_refund(run_id: str) -> None:
    with get_database_connection() as connection, database_transaction(connection):
        record_approval_decision(
            connection,
            run_id=run_id,
            approval_status=ApprovalStatus.REJECTED,
            new_state=AgentState.NEEDS_HUMAN_REVIEW,
        )
    logger.info(
        "Trusted rejection committed: run_id=%s decision=%s to_state=%s",
        run_id,
        ApprovalStatus.REJECTED.value,
        AgentState.NEEDS_HUMAN_REVIEW.value,
    )
    print("[APPROVAL]")
    print("REJECTED")
