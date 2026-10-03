"""Read-only gateway verification for ambiguous refund outcomes."""

import logging
import time
from collections.abc import Callable

from app.config import ApplicationSettings
from app.database.agent_runs import transition_agent_state
from app.database.connection import database_transaction, get_database_connection
from app.database.refunds import update_refund_status
from app.exceptions import GatewayUnavailableError, InvalidAgentStateError
from app.gateway.mock_payment_gateway import get_refund_status
from app.schemas.agent_run import AgentRun
from app.states import AgentState, RefundStatus
from app.workflow.refund_execution import record_verified_refund

logger = logging.getLogger(__name__)


def verify_refund_outcome(
    agent_run: AgentRun,
    *,
    settings: ApplicationSettings | None = None,
    sleep_function: Callable[[float], None] = time.sleep,
) -> None:
    if not agent_run.idempotency_key or not agent_run.refund_id:
        raise InvalidAgentStateError(
            f"Cannot verify '{agent_run.id}': refund checkpoint is incomplete."
        )

    print("[ADAPT]")
    print("Checking gateway status instead of retrying refund")
    gateway_transaction = None
    for attempt_number in range(1, 4):
        logger.info(
            "Querying gateway for ambiguous refund outcome: run_id=%s "
            "refund_id=%s attempt=%s",
            agent_run.id,
            agent_run.refund_id,
            attempt_number,
        )
        try:
            gateway_transaction = get_refund_status(
                agent_run.idempotency_key, settings=settings
            )
        except GatewayUnavailableError:
            logger.warning(
                "Gateway unavailable during refund verification: run_id=%s attempt=%s",
                agent_run.id,
                attempt_number,
            )
            gateway_transaction = None
        if gateway_transaction is not None:
            break
        if attempt_number < 3:
            sleep_function(float(attempt_number))

    if gateway_transaction is not None:
        record_verified_refund(agent_run.id, gateway_transaction)
        logger.info(
            "Gateway verification succeeded: run_id=%s refund_id=%s transaction_id=%s",
            agent_run.id,
            agent_run.refund_id,
            gateway_transaction.transaction_id,
        )
        print("[VERIFY]")
        print(f"Gateway transaction {gateway_transaction.transaction_id}")
        print(f"Status: {gateway_transaction.status}")
        return

    with get_database_connection() as connection, database_transaction(connection):
        update_refund_status(connection, agent_run.refund_id, RefundStatus.UNKNOWN)
        transition_agent_state(
            connection,
            agent_run.id,
            AgentState.NEEDS_HUMAN_REVIEW,
            last_observation=(
                "Refund outcome could not be verified after three status queries."
            ),
        )
    logger.error(
        "Refund outcome remains unknown after verification limit: "
        "run_id=%s refund_id=%s state=%s",
        agent_run.id,
        agent_run.refund_id,
        AgentState.NEEDS_HUMAN_REVIEW.value,
    )
    print("Refund outcome could not be verified safely.")
    print("Human review is required.")
    print("No additional refund will be issued automatically.")
