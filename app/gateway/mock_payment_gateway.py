"""Database-backed idempotent mock payment gateway."""

import logging

from app.config import ApplicationSettings, load_settings
from app.database.connection import database_transaction, get_database_connection
from app.database.gateway_transactions import (
    create_gateway_transaction,
    find_gateway_transaction_by_idempotency_key,
)
from app.exceptions import (
    DatabaseError,
    GatewayUnavailableError,
    PaymentGatewayError,
    PaymentGatewayTimeoutError,
)
from app.schemas.refund import GatewayRefundRequest, GatewayRefundResult

logger = logging.getLogger(__name__)


def issue_refund(
    request: GatewayRefundRequest,
    *,
    settings: ApplicationSettings | None = None,
) -> GatewayRefundResult:
    """Create one gateway transaction per idempotency key."""
    application_settings = settings or load_settings()
    transaction_was_created = False
    try:
        with (
            get_database_connection(application_settings) as connection,
            database_transaction(connection),
        ):
            gateway_transaction = find_gateway_transaction_by_idempotency_key(
                connection, request.idempotency_key
            )
            if gateway_transaction is None:
                gateway_transaction = create_gateway_transaction(connection, request)
                transaction_was_created = True
    except DatabaseError as exc:
        logger.exception(
            "Mock gateway refund operation failed: order_id=%s", request.order_id
        )
        raise PaymentGatewayError(f"Mock gateway refund request failed: {exc}") from exc

    logger.info(
        "Mock gateway transaction %s: order_id=%s transaction_id=%s",
        "created" if transaction_was_created else "reused",
        request.order_id,
        gateway_transaction.transaction_id,
    )

    if (
        transaction_was_created
        and application_settings.mock_gateway.simulate_timeout_after_commit
    ):
        logger.warning(
            "Mock gateway response timeout simulated after commit: "
            "order_id=%s transaction_id=%s",
            request.order_id,
            gateway_transaction.transaction_id,
        )
        raise PaymentGatewayTimeoutError(
            "Gateway response timed out after refund commit."
        )
    return gateway_transaction


def get_refund_status(
    idempotency_key: str,
    *,
    settings: ApplicationSettings | None = None,
) -> GatewayRefundResult | None:
    """Query external outcome without creating another refund."""
    application_settings = settings or load_settings()
    try:
        with get_database_connection(application_settings) as connection:
            gateway_transaction = find_gateway_transaction_by_idempotency_key(
                connection, idempotency_key
            )
        logger.info(
            "Mock gateway status queried: transaction_found=%s transaction_id=%s",
            gateway_transaction is not None,
            gateway_transaction.transaction_id if gateway_transaction else None,
        )
        return gateway_transaction
    except DatabaseError as exc:
        logger.warning("Mock gateway status query failed", exc_info=True)
        raise GatewayUnavailableError(
            f"Mock gateway status is unavailable: {exc}"
        ) from exc
