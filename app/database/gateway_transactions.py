"""Raw SQL storage used by the mock external payment provider."""

from datetime import datetime, timezone
from uuid import uuid4

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import DatabaseError
from app.schemas.refund import GatewayRefundRequest, GatewayRefundResult


def find_gateway_transaction_by_idempotency_key(
    connection: MySQLConnectionAbstract,
    idempotency_key: str,
) -> GatewayRefundResult | None:
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT transaction_id, idempotency_key, order_id,
                       amount, status, created_at
                FROM gateway_transactions
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            )
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not query mock gateway transaction: {exc}") from exc
    if row is None:
        return None
    try:
        return GatewayRefundResult.model_validate(row)
    except ValidationError as exc:
        raise DatabaseError(
            f"Mock gateway transaction contains invalid persisted data: {exc}"
        ) from exc


def create_gateway_transaction(
    connection: MySQLConnectionAbstract,
    request: GatewayRefundRequest,
) -> GatewayRefundResult:
    transaction_id = f"GTX_{uuid4().hex}"
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gateway_transactions (
                    transaction_id, idempotency_key, order_id,
                    amount, status, created_at
                )
                VALUES (%s, %s, %s, %s, 'SUCCESS', %s)
                """,
                (
                    transaction_id,
                    request.idempotency_key,
                    request.order_id,
                    request.amount,
                    timestamp,
                ),
            )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not create mock gateway transaction: {exc}"
        ) from exc

    return GatewayRefundResult(
        transaction_id=transaction_id,
        idempotency_key=request.idempotency_key,
        order_id=request.order_id,
        amount=request.amount,
        status="SUCCESS",
        created_at=timestamp,
    )
