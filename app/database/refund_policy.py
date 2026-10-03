"""Raw SQL operations for the trusted refund policy."""

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import DatabaseError, RecordNotFoundError
from app.schemas.policy import RefundPolicy


def get_active_refund_policy(
    connection: MySQLConnectionAbstract,
) -> RefundPolicy:
    """Load the single policy used by this narrow POC."""
    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, refund_window_days, auto_approval_limit
                FROM refund_policy
                ORDER BY id
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load refund policy: {exc}") from exc

    if row is None:
        raise RecordNotFoundError("No refund policy is configured.")
    try:
        return RefundPolicy.model_validate(row)
    except ValidationError as exc:
        raise DatabaseError(
            f"Refund policy contains invalid persisted data: {exc}"
        ) from exc
