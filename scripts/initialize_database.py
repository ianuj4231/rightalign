"""Create and initialize the configured MySQL database.

Run from the project root with:

    python scripts/initialize_database.py
"""

import re
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import ApplicationSettings, load_settings
from app.exceptions import ConfigurationError

REQUIRED_TABLES = {
    "tickets",
    "orders",
    "refund_policy",
    "agent_runs",
    "refunds",
    "gateway_transactions",
}


def _validate_database_name(database_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise ConfigurationError(
            "MYSQL_DATABASE may contain only letters, numbers, and underscores."
        )


def _read_sql_statements(sql_path: Path) -> list[str]:
    sql_text = sql_path.read_text(encoding="utf-8")
    return [statement.strip() for statement in sql_text.split(";") if statement.strip()]


def _connect_to_mysql(
    settings: ApplicationSettings,
    *,
    include_database: bool,
):
    connection_arguments = {
        "host": settings.database.host,
        "port": settings.database.port,
        "user": settings.database.user,
        "password": settings.database.password,
        "autocommit": False,
    }
    if include_database:
        connection_arguments["database"] = settings.database.name
    return mysql.connector.connect(**connection_arguments)


def _create_database(settings: ApplicationSettings) -> None:
    database_name = settings.database.name
    _validate_database_name(database_name)
    connection = _connect_to_mysql(settings, include_database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _load_existing_tables(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        return {row[0] for row in cursor.fetchall()}


def _apply_sql_file(connection, sql_path: Path) -> None:
    try:
        with connection.cursor() as cursor:
            for statement in _read_sql_statements(sql_path):
                cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _count_seed_records(connection) -> int:
    queries = (
        ("SELECT COUNT(*) FROM refund_policy WHERE id = %s", (1,)),
        ("SELECT COUNT(*) FROM orders WHERE id = %s", ("ORD456",)),
        ("SELECT COUNT(*) FROM tickets WHERE id = %s", ("T123",)),
    )
    record_count = 0
    with connection.cursor() as cursor:
        for query, parameters in queries:
            cursor.execute(query, parameters)
            record_count += int(cursor.fetchone()[0])
    return record_count


def initialize_database(settings: ApplicationSettings) -> None:
    """Create the database and apply the specification's schema and seed data."""
    _create_database(settings)
    connection = _connect_to_mysql(settings, include_database=True)
    try:
        existing_tables = _load_existing_tables(connection)
        relevant_existing_tables = existing_tables.intersection(REQUIRED_TABLES)

        if not relevant_existing_tables:
            _apply_sql_file(connection, PROJECT_ROOT / "sql" / "schema.sql")
            print("Applied sql/schema.sql")
        elif relevant_existing_tables == REQUIRED_TABLES:
            print("Schema already exists; skipped sql/schema.sql")
        else:
            missing_tables = sorted(REQUIRED_TABLES - relevant_existing_tables)
            raise RuntimeError(
                "Database contains a partial refund-operator schema. "
                f"Missing tables: {', '.join(missing_tables)}."
            )

        seed_record_count = _count_seed_records(connection)
        if seed_record_count == 0:
            _apply_sql_file(connection, PROJECT_ROOT / "sql" / "seed.sql")
            print("Applied sql/seed.sql")
        elif seed_record_count == 3:
            print("Seed records already exist; skipped sql/seed.sql")
        else:
            raise RuntimeError(
                "Database contains partial demo seed data. Expected policy 1, "
                "order ORD456, and ticket T123 together."
            )
    finally:
        connection.close()


def main() -> int:
    try:
        settings = load_settings(PROJECT_ROOT / "config" / "settings.yaml")
        initialize_database(settings)
    except (ConfigurationError, MySQLError, OSError, RuntimeError) as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Database '{settings.database.name}' initialized successfully at "
        f"{settings.database.host}:{settings.database.port}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
