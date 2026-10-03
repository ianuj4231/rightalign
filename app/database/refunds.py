"""Raw SQL operations for the application's local refund record."""

from datetime import datetime, timezone
from uuid import uuid4

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import DatabaseError, RecordNotFoundError
from app.schemas.refund import Refund
from app.states import RefundStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _validate_refund(row: dict, identifier: str) -> Refund:
    try:
        return Refund.model_validate(row)
    except ValidationError as exc:
        raise DatabaseError(
            f"Refund '{identifier}' contains invalid persisted data: {exc}"
        ) from exc


def create_refund(
    connection: MySQLConnectionAbstract,
    *,
    order_id: str,
    amount: int,
    idempotency_key: str,
) -> Refund:
    refund_id = f"RF_{uuid4().hex}"
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO refunds (
                    id, order_id, amount, idempotency_key,
                    gateway_transaction_id, status, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
                """,
                (
                    refund_id,
                    order_id,
                    amount,
                    idempotency_key,
                    RefundStatus.PENDING.value,
                    timestamp,
                    timestamp,
                ),
            )
    except MySQLError as exc:
        raise DatabaseError(
            f"Could not create refund for order '{order_id}': {exc}"
        ) from exc

    return Refund(
        id=refund_id,
        order_id=order_id,
        amount=amount,
        idempotency_key=idempotency_key,
        status=RefundStatus.PENDING,
        created_at=timestamp,
        updated_at=timestamp,
    )


def find_refund_by_idempotency_key(
    connection: MySQLConnectionAbstract,
    idempotency_key: str,
    *,
    for_update: bool = False,
) -> Refund | None:
    query = """
        SELECT id, order_id, amount, idempotency_key,
               gateway_transaction_id, status, created_at, updated_at
        FROM refunds
        WHERE idempotency_key = %s
    """
    if for_update:
        query += " FOR UPDATE"
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (idempotency_key,))
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load refund by idempotency key: {exc}") from exc
    return _validate_refund(row, idempotency_key) if row is not None else None


def get_refund_by_id(
    connection: MySQLConnectionAbstract,
    refund_id: str,
    *,
    for_update: bool = False,
) -> Refund:
    query = """
        SELECT id, order_id, amount, idempotency_key,
               gateway_transaction_id, status, created_at, updated_at
        FROM refunds
        WHERE id = %s
    """
    if for_update:
        query += " FOR UPDATE"
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (refund_id,))
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load refund '{refund_id}': {exc}") from exc
    if row is None:
        raise RecordNotFoundError(f"Refund '{refund_id}' was not found.")
    return _validate_refund(row, refund_id)


def update_refund_status(
    connection: MySQLConnectionAbstract,
    refund_id: str,
    status: RefundStatus,
    *,
    gateway_transaction_id: str | None = None,
) -> None:
    timestamp = _utc_now()
    try:
        with connection.cursor() as cursor:
            if gateway_transaction_id is None:
                cursor.execute(
                    "UPDATE refunds SET status = %s, updated_at = %s WHERE id = %s",
                    (status.value, timestamp, refund_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE refunds
                    SET status = %s, gateway_transaction_id = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (status.value, gateway_transaction_id, timestamp, refund_id),
                )
            if cursor.rowcount != 1:
                raise RecordNotFoundError(f"Refund '{refund_id}' was not found.")
    except MySQLError as exc:
        raise DatabaseError(f"Could not update refund '{refund_id}': {exc}") from exc
