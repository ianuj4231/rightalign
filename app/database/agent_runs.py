"""Raw SQL operations for durable workflow state."""

from datetime import datetime, timezone
from uuid import uuid4

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import (
    DatabaseError,
    InvalidAgentStateError,
    RecordNotFoundError,
)
from app.schemas.agent_run import AgentRun
from app.states import AgentState, ApprovalStatus, validate_state_transition

AGENT_RUN_COLUMNS = """
    id, ticket_id, order_id, intent, current_state, policy_passed,
    approval_status, refund_id, idempotency_key, last_observation,
    created_at, updated_at
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _validate_agent_run(row: dict) -> AgentRun:
    try:
        return AgentRun.model_validate(row)
    except ValidationError as exc:
        run_identifier = row.get("id", "unknown")
        raise InvalidAgentStateError(
            f"Agent run '{run_identifier}' contains invalid persisted state: {exc}"
        ) from exc


def create_agent_run(
    connection: MySQLConnectionAbstract,
    ticket_id: str,
) -> AgentRun:
    run_id = f"RUN_{uuid4().hex}"
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs (
                    id, ticket_id, current_state, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, ticket_id, AgentState.STARTED.value, timestamp, timestamp),
            )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not create agent run for ticket '{ticket_id}': {exc}"
        ) from exc

    return AgentRun(
        id=run_id,
        ticket_id=ticket_id,
        current_state=AgentState.STARTED,
        created_at=timestamp,
        updated_at=timestamp,
    )


def get_agent_run_by_id(
    connection: MySQLConnectionAbstract,
    run_id: str,
    *,
    for_update: bool = False,
) -> AgentRun:
    query = f"SELECT {AGENT_RUN_COLUMNS} FROM agent_runs WHERE id = %s"
    if for_update:
        query += " FOR UPDATE"
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (run_id,))
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load agent run '{run_id}': {exc}") from exc
    if row is None:
        raise RecordNotFoundError(f"Agent run '{run_id}' was not found.")
    return _validate_agent_run(row)


def find_active_agent_run_for_ticket(
    connection: MySQLConnectionAbstract,
    ticket_id: str,
) -> AgentRun | None:
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT {AGENT_RUN_COLUMNS}
                FROM agent_runs
                WHERE ticket_id = %s AND current_state <> %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ticket_id, AgentState.COMPLETE.value),
            )
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not find active agent run for ticket '{ticket_id}': {exc}"
        ) from exc
    return _validate_agent_run(row) if row is not None else None


def transition_agent_state(
    connection: MySQLConnectionAbstract,
    run_id: str,
    new_state: AgentState,
    *,
    last_observation: str | None = None,
) -> AgentRun:
    current_run = get_agent_run_by_id(connection, run_id, for_update=True)
    validate_state_transition(current_run.current_state, new_state)
    timestamp = _utc_now()
    observation = (
        last_observation
        if last_observation is not None
        else current_run.last_observation
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs
                SET current_state = %s, last_observation = %s, updated_at = %s
                WHERE id = %s AND current_state = %s
                """,
                (
                    new_state.value,
                    observation,
                    timestamp,
                    run_id,
                    current_run.current_state.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidAgentStateError(
                    f"Agent run '{run_id}' changed while transitioning; retry safely."
                )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not transition agent run '{run_id}': {exc}"
        ) from exc
    return current_run.model_copy(
        update={
            "current_state": new_state,
            "last_observation": observation,
            "updated_at": timestamp,
        }
    )


def record_intent_understanding(
    connection: MySQLConnectionAbstract,
    *,
    run_id: str,
    order_id: str,
    intent: str,
    last_observation: str,
) -> None:
    current_run = get_agent_run_by_id(connection, run_id, for_update=True)
    validate_state_transition(current_run.current_state, AgentState.INTENT_UNDERSTOOD)
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs
                SET order_id = %s, intent = %s, current_state = %s,
                    last_observation = %s, updated_at = %s
                WHERE id = %s AND current_state = %s
                """,
                (
                    order_id,
                    intent,
                    AgentState.INTENT_UNDERSTOOD.value,
                    last_observation,
                    timestamp,
                    run_id,
                    current_run.current_state.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidAgentStateError(
                    f"Agent run '{run_id}' changed while recording intent."
                )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not record intent for run '{run_id}': {exc}"
        ) from exc


def record_policy_decision(
    connection: MySQLConnectionAbstract,
    *,
    run_id: str,
    policy_passed: bool,
    approval_status: ApprovalStatus | None,
    last_observation: str,
) -> None:
    current_run = get_agent_run_by_id(connection, run_id, for_update=True)
    validate_state_transition(current_run.current_state, AgentState.POLICY_CHECKED)
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs
                SET policy_passed = %s, approval_status = %s,
                    current_state = %s, last_observation = %s, updated_at = %s
                WHERE id = %s AND current_state = %s
                """,
                (
                    policy_passed,
                    approval_status.value if approval_status else None,
                    AgentState.POLICY_CHECKED.value,
                    last_observation,
                    timestamp,
                    run_id,
                    current_run.current_state.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidAgentStateError(
                    f"Agent run '{run_id}' changed while recording policy decision."
                )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not record policy decision for run '{run_id}': {exc}"
        ) from exc


def record_approval_decision(
    connection: MySQLConnectionAbstract,
    *,
    run_id: str,
    approval_status: ApprovalStatus,
    new_state: AgentState,
) -> None:
    current_run = get_agent_run_by_id(connection, run_id, for_update=True)
    if current_run.current_state != AgentState.WAITING_APPROVAL:
        raise InvalidAgentStateError(
            f"Cannot record approval for '{run_id}': workflow is "
            f"{current_run.current_state.value}, not WAITING_APPROVAL."
        )
    if current_run.approval_status != ApprovalStatus.PENDING:
        value = (
            current_run.approval_status.value
            if current_run.approval_status
            else "missing"
        )
        raise InvalidAgentStateError(
            f"Cannot record approval for '{run_id}': approval status is {value}."
        )
    validate_state_transition(current_run.current_state, new_state)
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs
                SET approval_status = %s, current_state = %s,
                    last_observation = %s, updated_at = %s
                WHERE id = %s AND current_state = %s AND approval_status = %s
                """,
                (
                    approval_status.value,
                    new_state.value,
                    f"Trusted human decision recorded: {approval_status.value}",
                    timestamp,
                    run_id,
                    AgentState.WAITING_APPROVAL.value,
                    ApprovalStatus.PENDING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidAgentStateError(
                    f"Approval state for '{run_id}' changed; no decision was applied."
                )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not record approval for run '{run_id}': {exc}"
        ) from exc


def record_refund_execution_checkpoint(
    connection: MySQLConnectionAbstract,
    *,
    run_id: str,
    refund_id: str,
    idempotency_key: str,
) -> None:
    current_run = get_agent_run_by_id(connection, run_id, for_update=True)
    validate_state_transition(current_run.current_state, AgentState.REFUND_EXECUTING)
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE agent_runs
                SET refund_id = %s, idempotency_key = %s, current_state = %s,
                    last_observation = %s, updated_at = %s
                WHERE id = %s AND current_state = %s
                """,
                (
                    refund_id,
                    idempotency_key,
                    AgentState.REFUND_EXECUTING.value,
                    "Refund execution checkpoint persisted before gateway call.",
                    timestamp,
                    run_id,
                    current_run.current_state.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidAgentStateError(
                    f"Agent run '{run_id}' changed before refund checkpoint."
                )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not checkpoint refund execution for run '{run_id}': {exc}"
        ) from exc
