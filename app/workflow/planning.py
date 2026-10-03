"""Informational refund workflow planning."""

import logging

from app.database.agent_runs import transition_agent_state
from app.database.connection import database_transaction, get_database_connection
from app.schemas.agent_run import AgentRun
from app.states import AgentState

logger = logging.getLogger(__name__)

REFUND_PLAN = (
    "Retrieve order",
    "Retrieve refund policy",
    "Check eligibility",
    "Determine approval requirement",
    "Execute refund if authorized",
    "Verify refund",
    "Resolve ticket",
)


def create_refund_plan(agent_run: AgentRun) -> tuple[str, ...]:
    """Display the fixed plan and persist progress without granting permission."""
    print("[PLAN]")
    for step_number, description in enumerate(REFUND_PLAN, start=1):
        print(f"{step_number}. {description}")

    with get_database_connection() as connection, database_transaction(connection):
        transition_agent_state(
            connection,
            agent_run.id,
            AgentState.PLANNED,
            last_observation="Refund workflow plan created.",
        )
    logger.info(
        "Informational plan completed: run_id=%s state=%s",
        agent_run.id,
        AgentState.PLANNED.value,
    )
    return REFUND_PLAN
