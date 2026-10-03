"""Raw deterministic workflow loop."""

import logging

from app.config import ApplicationSettings, load_settings
from app.database.agent_runs import (
    create_agent_run,
    find_active_agent_run_for_ticket,
    get_agent_run_by_id,
)
from app.database.connection import database_transaction, get_database_connection
from app.database.tickets import get_ticket_by_id
from app.exceptions import InvalidAgentStateError
from app.llm.base import LLMClient
from app.llm.factory import create_llm
from app.schemas.agent_run import AgentRun
from app.schemas.ticket import TicketStatus
from app.states import AgentState
from app.workflow.completion import complete_ticket
from app.workflow.planning import create_refund_plan
from app.workflow.policy_check import check_refund_policy, route_after_policy_check
from app.workflow.refund_execution import execute_refund, recover_interrupted_refund
from app.workflow.refund_verification import verify_refund_outcome
from app.workflow.understand import understand_customer_request

logger = logging.getLogger(__name__)


def load_agent_run(run_id: str) -> AgentRun:
    with get_database_connection() as connection:
        return get_agent_run_by_id(connection, run_id)


def start_or_resume_ticket(
    ticket_id: str,
    *,
    settings: ApplicationSettings | None = None,
    llm_client: LLMClient | None = None,
) -> str:
    """Serialize active-run lookup and creation on the trusted ticket row."""
    application_settings = settings or load_settings()
    created_new_run = False
    with (
        get_database_connection(application_settings) as connection,
        database_transaction(connection),
    ):
        ticket = get_ticket_by_id(connection, ticket_id, for_update=True)
        active_run = find_active_agent_run_for_ticket(connection, ticket_id)
        if active_run is None:
            if ticket.status == TicketStatus.RESOLVED:
                raise InvalidAgentStateError(
                    f"Ticket '{ticket_id}' is already RESOLVED; a new refund run "
                    "will not be created."
                )
            active_run = create_agent_run(connection, ticket_id)
            created_new_run = True

    logger.info(
        "Agent run %s: run_id=%s ticket_id=%s state=%s",
        "created" if created_new_run else "resumed",
        active_run.id,
        ticket_id,
        active_run.current_state.value,
    )

    print("[GOAL]")
    print(f"Resolve ticket {ticket_id}")
    print(f"Run: {active_run.id}")
    run_agent(
        active_run.id,
        settings=application_settings,
        llm_client=llm_client,
    )
    return active_run.id


def run_agent(
    run_id: str,
    *,
    settings: ApplicationSettings | None = None,
    llm_client: LLMClient | None = None,
) -> None:
    """Reload persisted state before dispatching every allowed handler."""
    application_settings = settings or load_settings()
    selected_llm = llm_client

    while True:
        agent_run = load_agent_run(run_id)
        logger.info(
            "Dispatching persisted workflow state: run_id=%s ticket_id=%s state=%s",
            agent_run.id,
            agent_run.ticket_id,
            agent_run.current_state.value,
        )

        match agent_run.current_state:
            case AgentState.STARTED:
                if selected_llm is None:
                    selected_llm = create_llm(application_settings)
                understand_customer_request(agent_run, selected_llm)
            case AgentState.INTENT_UNDERSTOOD:
                create_refund_plan(agent_run)
            case AgentState.PLANNED:
                check_refund_policy(agent_run)
            case AgentState.POLICY_CHECKED:
                route_after_policy_check(agent_run)
            case AgentState.WAITING_APPROVAL:
                print("[STATE]")
                print("WAITING_APPROVAL")
                print("Human approval required.")
                return
            case AgentState.REFUND_READY:
                execute_refund(agent_run, settings=application_settings)
            case AgentState.REFUND_EXECUTING:
                recover_interrupted_refund(agent_run)
            case AgentState.REFUND_OUTCOME_UNKNOWN:
                verify_refund_outcome(agent_run, settings=application_settings)
            case AgentState.REFUND_VERIFIED:
                complete_ticket(agent_run)
            case AgentState.NEEDS_HUMAN_REVIEW:
                print("[STATE]")
                print("NEEDS_HUMAN_REVIEW")
                return
            case AgentState.COMPLETE:
                print("[STATE]")
                print("COMPLETE")
                return
            case _:
                raise InvalidAgentStateError(
                    f"Cannot resume '{run_id}': workflow state "
                    f"'{agent_run.current_state}' is invalid."
                )
