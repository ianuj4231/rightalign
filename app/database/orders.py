"""Raw SQL operations for trusted order facts."""

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import DatabaseError, RecordNotFoundError
from app.schemas.order import Order, OrderRefundStatus


def get_order_by_id(
    connection: MySQLConnectionAbstract,
    order_id: str,
    *,
    for_update: bool = False,
) -> Order:
    query = """
        SELECT id, amount, purchase_date, status, refund_status
        FROM orders
        WHERE id = %s
    """
    if for_update:
        query += " FOR UPDATE"

    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (order_id,))
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load order '{order_id}': {exc}") from exc

    if row is None:
        raise RecordNotFoundError(f"Order '{order_id}' was not found.")
    try:
        return Order.model_validate(row)
    except ValidationError as exc:
        raise DatabaseError(
            f"Order '{order_id}' contains invalid persisted data: {exc}"
        ) from exc


def update_order_refund_status(
    connection: MySQLConnectionAbstract,
    order_id: str,
    refund_status: OrderRefundStatus,
) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET refund_status = %s WHERE id = %s",
                (refund_status.value, order_id),
            )
            if cursor.rowcount != 1:
                raise RecordNotFoundError(f"Order '{order_id}' was not found.")
    except MySQLError as exc:
        raise DatabaseError(f"Could not update order '{order_id}': {exc}") from exc
