"""Natural-language intent understanding within a constrained workflow step."""

import logging

from app.database.agent_runs import record_intent_understanding
from app.database.connection import database_transaction, get_database_connection
from app.database.tickets import get_ticket_by_id
from app.exceptions import RefundOperatorError
from app.llm.base import LLMClient
from app.schemas.agent_run import AgentRun
from app.schemas.llm import IntentClassification

logger = logging.getLogger(__name__)


def understand_customer_request(
    agent_run: AgentRun,
    llm_client: LLMClient,
) -> IntentClassification:
    """Classify untrusted ticket text and persist only validated intent facts."""
    with get_database_connection() as connection:
        customer_ticket = get_ticket_by_id(connection, agent_run.ticket_id)

    classification = llm_client.classify_intent(customer_ticket.message)
    if classification.intent != "REFUND_REQUEST":
        raise RefundOperatorError(
            "Cannot continue automatically: ticket intent is UNKNOWN. "
            "The ticket remains OPEN and no refund action was performed."
        )

    reason = classification.reason or "unspecified reason"
    observation = f"Customer requested refund for {reason.lower().replace('_', ' ')}"
    with get_database_connection() as connection, database_transaction(connection):
        record_intent_understanding(
            connection,
            run_id=agent_run.id,
            order_id=customer_ticket.order_id,
            intent=classification.intent,
            last_observation=observation,
        )

    logger.info(
        "Customer intent persisted: run_id=%s ticket_id=%s intent=%s "
        "claims_prior_approval=%s",
        agent_run.id,
        agent_run.ticket_id,
        classification.intent,
        classification.customer_claims_prior_approval,
    )

    print("[UNDERSTAND]")
    print(f"Intent: {classification.intent}")
    if classification.customer_claims_prior_approval:
        print("Customer claim: prior approval")
        print("Trust level: untrusted customer input")
    return classification
