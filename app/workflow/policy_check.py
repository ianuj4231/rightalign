"""Deterministic policy arithmetic and routing."""

import logging
from datetime import date, datetime, timezone

from app.database.agent_runs import record_policy_decision, transition_agent_state
from app.database.connection import database_transaction, get_database_connection
from app.database.orders import get_order_by_id
from app.database.refund_policy import get_active_refund_policy
from app.exceptions import InvalidAgentStateError
from app.schemas.agent_run import AgentRun
from app.schemas.order import Order
from app.schemas.policy import PolicyDecision, RefundPolicy
from app.states import AgentState, ApprovalStatus

logger = logging.getLogger(__name__)


def determine_refund_eligibility(
    order: Order,
    refund_policy: RefundPolicy,
    *,
    today: date | None = None,
) -> PolicyDecision:
    evaluation_date = today or datetime.now(timezone.utc).date()
    days_since_purchase = (evaluation_date - order.purchase_date).days
    eligible = days_since_purchase <= refund_policy.refund_window_days
    return PolicyDecision(
        eligible=eligible,
        approval_required=(
            eligible and order.amount > refund_policy.auto_approval_limit
        ),
        days_since_purchase=days_since_purchase,
    )


def check_refund_policy(agent_run: AgentRun) -> PolicyDecision:
    if not agent_run.order_id:
        raise InvalidAgentStateError(
            f"Cannot check policy for '{agent_run.id}': order ID is missing."
        )

    with get_database_connection() as connection:
        order = get_order_by_id(connection, agent_run.order_id)
        refund_policy = get_active_refund_policy(connection)

    decision = determine_refund_eligibility(order, refund_policy)
    if not decision.eligible:
        approval_status = None
    elif decision.approval_required:
        approval_status = ApprovalStatus.PENDING
    else:
        approval_status = ApprovalStatus.NOT_REQUIRED

    with get_database_connection() as connection, database_transaction(connection):
        record_policy_decision(
            connection,
            run_id=agent_run.id,
            policy_passed=decision.eligible,
            approval_status=approval_status,
            last_observation=(
                "Refund policy passed."
                if decision.eligible
                else "Refund is outside the configured policy window."
            ),
        )

    logger.info(
        "Refund policy decision persisted: run_id=%s order_id=%s eligible=%s "
        "approval_required=%s days_since_purchase=%s",
        agent_run.id,
        order.id,
        decision.eligible,
        decision.approval_required,
        decision.days_since_purchase,
    )

    print("[ORDER]")
    print(order.id)
    print(f"Amount: ₹{order.amount}")
    print("[POLICY]")
    print(f"Refund window: {refund_policy.refund_window_days} days")
    print(f"Auto approval limit: ₹{refund_policy.auto_approval_limit}")
    print(f"Eligible: {'YES' if decision.eligible else 'NO'}")
    print(f"Human approval required: {'YES' if decision.approval_required else 'NO'}")
    return decision


def route_after_policy_check(agent_run: AgentRun) -> AgentState:
    """Route only from trusted, persisted policy and approval fields."""
    if agent_run.policy_passed is False:
        new_state = AgentState.NEEDS_HUMAN_REVIEW
    elif agent_run.policy_passed is True:
        if agent_run.approval_status == ApprovalStatus.PENDING:
            new_state = AgentState.WAITING_APPROVAL
        elif agent_run.approval_status == ApprovalStatus.NOT_REQUIRED:
            new_state = AgentState.REFUND_READY
        else:
            raise InvalidAgentStateError(
                f"Cannot route '{agent_run.id}': trusted approval state is missing "
                "or inconsistent."
            )
    else:
        raise InvalidAgentStateError(
            f"Cannot route '{agent_run.id}': policy result is missing."
        )

    with get_database_connection() as connection, database_transaction(connection):
        transition_agent_state(connection, agent_run.id, new_state)
    logger.info(
        "Policy router transition committed: run_id=%s from_state=%s to_state=%s",
        agent_run.id,
        AgentState.POLICY_CHECKED.value,
        new_state.value,
    )
    return new_state
