"""Verified customer-outcome completion."""

import logging

from app.database.agent_runs import get_agent_run_by_id, transition_agent_state
from app.database.connection import database_transaction, get_database_connection
from app.database.refunds import get_refund_by_id
from app.database.tickets import update_ticket_status
from app.exceptions import InvalidAgentStateError
from app.schemas.agent_run import AgentRun
from app.schemas.ticket import TicketStatus
from app.states import AgentState, RefundStatus

logger = logging.getLogger(__name__)


def complete_ticket(agent_run: AgentRun) -> None:
    with get_database_connection() as connection, database_transaction(connection):
        current_run = get_agent_run_by_id(connection, agent_run.id, for_update=True)
        if current_run.current_state != AgentState.REFUND_VERIFIED:
            raise InvalidAgentStateError(
                f"Cannot complete ticket from state {current_run.current_state.value}."
            )
        if not current_run.refund_id:
            raise InvalidAgentStateError(
                "Cannot complete ticket: verified refund ID is missing."
            )
        local_refund = get_refund_by_id(
            connection, current_run.refund_id, for_update=True
        )
        if (
            local_refund.status != RefundStatus.SUCCESS
            or not local_refund.gateway_transaction_id
        ):
            raise InvalidAgentStateError(
                "Cannot complete ticket: refund success is not verified."
            )
        update_ticket_status(connection, current_run.ticket_id, TicketStatus.RESOLVED)
        transition_agent_state(
            connection,
            current_run.id,
            AgentState.COMPLETE,
            last_observation="Verified refund completed and ticket resolved.",
        )

    logger.info(
        "Ticket completion committed: run_id=%s ticket_id=%s refund_id=%s state=%s",
        agent_run.id,
        agent_run.ticket_id,
        agent_run.refund_id,
        AgentState.COMPLETE.value,
    )

    print("[COMPLETE]")
    print(f"Ticket {agent_run.ticket_id} resolved")
    print(f"Refund {agent_run.refund_id} verified")
