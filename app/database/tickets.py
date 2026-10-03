"""Raw SQL operations for support tickets."""

from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract
from pydantic import ValidationError

from app.exceptions import DatabaseError, RecordNotFoundError
from app.schemas.ticket import Ticket, TicketStatus


def get_ticket_by_id(
    connection: MySQLConnectionAbstract,
    ticket_id: str,
    *,
    for_update: bool = False,
) -> Ticket:
    """Load a ticket, optionally locking it for active-run creation."""
    query = """
        SELECT id, order_id, message, status
        FROM tickets
        WHERE id = %s
    """
    if for_update:
        query += " FOR UPDATE"

    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (ticket_id,))
            row = cursor.fetchone()
    except MySQLError as exc:
        raise DatabaseError(f"Could not load ticket '{ticket_id}': {exc}") from exc

    if row is None:
        raise RecordNotFoundError(f"Ticket '{ticket_id}' was not found.")
    try:
        return Ticket.model_validate(row)
    except ValidationError as exc:
        raise DatabaseError(
            f"Ticket '{ticket_id}' contains invalid persisted data: {exc}"
        ) from exc


def update_ticket_status(
    connection: MySQLConnectionAbstract,
    ticket_id: str,
    status: TicketStatus,
) -> None:
    """Update the customer-facing completion status."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tickets SET status = %s WHERE id = %s",
                (status.value, ticket_id),
            )
            if cursor.rowcount != 1:
                raise RecordNotFoundError(f"Ticket '{ticket_id}' was not found.")
    except MySQLError as exc:
        raise DatabaseError(f"Could not update ticket '{ticket_id}': {exc}") from exc
