"""Authorized refund checkpointing and gateway execution."""

import logging

from app.config import ApplicationSettings
from app.database.agent_runs import (
    get_agent_run_by_id,
    record_refund_execution_checkpoint,
    transition_agent_state,
)
from app.database.connection import database_transaction, get_database_connection
from app.database.orders import get_order_by_id, update_order_refund_status
from app.database.refunds import (
    create_refund,
    find_refund_by_idempotency_key,
    get_refund_by_id,
    update_refund_status,
)
from app.exceptions import InvalidAgentStateError, PaymentGatewayTimeoutError
from app.gateway.mock_payment_gateway import issue_refund
from app.schemas.agent_run import AgentRun
from app.schemas.order import OrderRefundStatus
from app.schemas.refund import GatewayRefundRequest, GatewayRefundResult
from app.states import AgentState, ApprovalStatus, RefundStatus

logger = logging.getLogger(__name__)


def _validate_refund_authorization(agent_run: AgentRun) -> None:
    if agent_run.current_state != AgentState.REFUND_READY:
        raise InvalidAgentStateError(
            f"Cannot execute refund from state {agent_run.current_state.value}."
        )
    if agent_run.policy_passed is not True:
        raise InvalidAgentStateError("Cannot execute refund: policy has not passed.")
    if agent_run.approval_status not in {
        ApprovalStatus.NOT_REQUIRED,
        ApprovalStatus.APPROVED,
    }:
        raise InvalidAgentStateError(
            "Cannot execute refund: human approval is still pending or missing."
        )
    if not agent_run.order_id:
        raise InvalidAgentStateError("Cannot execute refund: order ID is missing.")


def record_verified_refund(
    run_id: str,
    gateway_transaction: GatewayRefundResult,
) -> None:
    """Atomically align local refund, order, and workflow with gateway truth."""
    with get_database_connection() as connection, database_transaction(connection):
        current_run = get_agent_run_by_id(connection, run_id, for_update=True)
        if current_run.current_state not in {
            AgentState.REFUND_EXECUTING,
            AgentState.REFUND_OUTCOME_UNKNOWN,
        }:
            raise InvalidAgentStateError(
                f"Cannot verify refund from state {current_run.current_state.value}."
            )
        if not current_run.refund_id or not current_run.order_id:
            raise InvalidAgentStateError(
                f"Cannot verify '{run_id}': refund or order ID is missing."
            )
        if current_run.idempotency_key != gateway_transaction.idempotency_key:
            raise InvalidAgentStateError(
                "Gateway idempotency key does not match the persisted refund key."
            )

        local_refund = get_refund_by_id(
            connection, current_run.refund_id, for_update=True
        )
        if (
            local_refund.order_id != gateway_transaction.order_id
            or local_refund.amount != gateway_transaction.amount
        ):
            raise InvalidAgentStateError(
                "Gateway transaction does not match the trusted local refund facts."
            )

        update_refund_status(
            connection,
            local_refund.id,
            RefundStatus.SUCCESS,
            gateway_transaction_id=gateway_transaction.transaction_id,
        )
        update_order_refund_status(
            connection,
            current_run.order_id,
            OrderRefundStatus.REFUNDED,
        )
        transition_agent_state(
            connection,
            run_id,
            AgentState.REFUND_VERIFIED,
            last_observation=(
                "Refund verified with gateway transaction "
                f"{gateway_transaction.transaction_id}"
            ),
        )

    logger.info(
        "Refund verification committed: run_id=%s order_id=%s refund_id=%s "
        "transaction_id=%s state=%s",
        run_id,
        gateway_transaction.order_id,
        local_refund.id,
        gateway_transaction.transaction_id,
        AgentState.REFUND_VERIFIED.value,
    )


def execute_refund(
    agent_run: AgentRun,
    *,
    settings: ApplicationSettings | None = None,
) -> None:
    """Commit a durable checkpoint before calling the payment gateway."""
    _validate_refund_authorization(agent_run)

    with get_database_connection() as connection, database_transaction(connection):
        locked_run = get_agent_run_by_id(connection, agent_run.id, for_update=True)
        _validate_refund_authorization(locked_run)
        order = get_order_by_id(connection, locked_run.order_id, for_update=True)
        expected_key = f"refund_{order.id}"
        if locked_run.idempotency_key and locked_run.idempotency_key != expected_key:
            raise InvalidAgentStateError(
                "Persisted idempotency key does not match the trusted order."
            )

        local_refund = find_refund_by_idempotency_key(
            connection, expected_key, for_update=True
        )
        if local_refund is None:
            local_refund = create_refund(
                connection,
                order_id=order.id,
                amount=order.amount,
                idempotency_key=expected_key,
            )
        elif local_refund.order_id != order.id or local_refund.amount != order.amount:
            raise InvalidAgentStateError(
                "Existing idempotent refund does not match trusted order facts."
            )

        record_refund_execution_checkpoint(
            connection,
            run_id=locked_run.id,
            refund_id=local_refund.id,
            idempotency_key=expected_key,
        )

    logger.info(
        "Refund execution checkpoint committed before gateway call: "
        "run_id=%s order_id=%s refund_id=%s state=%s",
        agent_run.id,
        order.id,
        local_refund.id,
        AgentState.REFUND_EXECUTING.value,
    )

    print("[EXECUTE]")
    print(f"Refund ID: {local_refund.id}")
    print(f"Idempotency key: {expected_key}")

    request = GatewayRefundRequest(
        order_id=order.id,
        amount=order.amount,
        idempotency_key=expected_key,
    )
    try:
        gateway_transaction = issue_refund(request, settings=settings)
    except PaymentGatewayTimeoutError:
        with get_database_connection() as connection, database_transaction(connection):
            update_refund_status(connection, local_refund.id, RefundStatus.UNKNOWN)
            transition_agent_state(
                connection,
                agent_run.id,
                AgentState.REFUND_OUTCOME_UNKNOWN,
                last_observation=(
                    "Gateway timed out after refund request; actual outcome is unknown."
                ),
            )
        logger.warning(
            "Gateway timeout recorded as unknown outcome: run_id=%s order_id=%s "
            "refund_id=%s state=%s",
            agent_run.id,
            order.id,
            local_refund.id,
            AgentState.REFUND_OUTCOME_UNKNOWN.value,
        )
        print("[GATEWAY]")
        print("Request timed out")
        print("[OBSERVE]")
        print("External outcome unknown")
        return

    record_verified_refund(agent_run.id, gateway_transaction)


def recover_interrupted_refund(agent_run: AgentRun) -> None:
    """Convert an interrupted execution checkpoint into verification work."""
    if not agent_run.refund_id or not agent_run.idempotency_key:
        raise InvalidAgentStateError(
            f"Cannot recover '{agent_run.id}': refund checkpoint is incomplete."
        )
    with get_database_connection() as connection, database_transaction(connection):
        update_refund_status(connection, agent_run.refund_id, RefundStatus.UNKNOWN)
        transition_agent_state(
            connection,
            agent_run.id,
            AgentState.REFUND_OUTCOME_UNKNOWN,
            last_observation=(
                "Recovered from interrupted refund execution; external outcome "
                "must be verified."
            ),
        )
    logger.warning(
        "Interrupted refund recovered for verification without re-execution: "
        "run_id=%s refund_id=%s state=%s",
        agent_run.id,
        agent_run.refund_id,
        AgentState.REFUND_OUTCOME_UNKNOWN.value,
    )
