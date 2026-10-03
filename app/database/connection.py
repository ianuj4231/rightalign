"""Centralized MySQL connection and transaction management."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.abstracts import MySQLConnectionAbstract

from app.config import ApplicationSettings, load_settings
from app.exceptions import DatabaseError

logger = logging.getLogger(__name__)


@contextmanager
def get_database_connection(
    settings: ApplicationSettings | None = None,
) -> Iterator[MySQLConnectionAbstract]:
    """Open and always close one configured MySQL connection."""
    application_settings = settings or load_settings()
    try:
        connection = mysql.connector.connect(
            host=application_settings.database.host,
            port=application_settings.database.port,
            database=application_settings.database.name,
            user=application_settings.database.user,
            password=application_settings.database.password,
            autocommit=False,
        )
    except MySQLError as exc:
        logger.exception(
            "MySQL connection failed: host=%s port=%s database=%s",
            application_settings.database.host,
            application_settings.database.port,
            application_settings.database.name,
        )
        raise DatabaseError(f"Could not connect to MySQL: {exc}") from exc

    try:
        yield connection
    finally:
        if connection.is_connected():
            connection.close()


@contextmanager
def database_transaction(
    connection: MySQLConnectionAbstract,
) -> Iterator[MySQLConnectionAbstract]:
    """Commit a unit of work or roll it back without hiding its cause."""
    try:
        yield connection
        connection.commit()
    except Exception as exc:
        logger.exception("Database transaction failed; rolling back")
        try:
            connection.rollback()
        except MySQLError as rollback_error:
            logger.exception("Database transaction rollback failed")
            raise DatabaseError(
                f"Database operation failed and rollback also failed: {rollback_error}"
            ) from exc
        if isinstance(exc, MySQLError):
            raise DatabaseError(f"Database operation failed: {exc}") from exc
        raise
