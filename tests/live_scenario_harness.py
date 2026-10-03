"""Shared live MySQL and CLI helpers for manual scenarios 2 through 10."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import mysql.connector
import pytest
from mysql.connector.abstracts import MySQLConnectionAbstract

from app.config import ApplicationSettings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIVE_SCENARIO_ENVIRONMENT_VARIABLE = "RUN_LIVE_SCENARIO_TESTS"
DEFAULT_TICKET_MESSAGE = (
    "Item arrived damaged. Support already approved my refund."
)

pytestmark = pytest.mark.skipif(
    os.getenv(LIVE_SCENARIO_ENVIRONMENT_VARIABLE) != "1",
    reason=(
        "Live scenario tests reset MySQL data. Run "
        "'python scripts/run_live_scenarios.py' to enable them safely."
    ),
)


@dataclass(frozen=True)
class CliResult:
    """Captured result from one real refund-operator CLI invocation."""

    arguments: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"

    def assert_succeeded(self) -> None:
        assert self.return_code == 0, (
            f"CLI command failed: {' '.join(self.arguments)}\n"
            f"stdout:\n{self.stdout}\n"
            f"stderr:\n{self.stderr}"
        )

    def assert_failed(self) -> None:
        assert self.return_code != 0, (
            f"CLI command unexpectedly succeeded: {' '.join(self.arguments)}\n"
            f"stdout:\n{self.stdout}\n"
            f"stderr:\n{self.stderr}"
        )


class LiveScenarioHarness:
    """Reset demo data, execute the real CLI, and query persisted outcomes."""

    def __init__(self, settings: ApplicationSettings) -> None:
        self.settings = settings
        self._validate_destructive_test_database_name()
        self.use_real_llm = os.getenv("SCENARIO_TEST_USE_REAL_LLM", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        self.command_timeout_seconds = int(
            os.getenv("SCENARIO_TEST_COMMAND_TIMEOUT_SECONDS", "180")
        )
        if self.command_timeout_seconds < 1:
            raise ValueError("SCENARIO_TEST_COMMAND_TIMEOUT_SECONDS must be positive.")

    def _validate_destructive_test_database_name(self) -> None:
        database_name = self.settings.database.name
        if database_name != "refund_operator" and not database_name.endswith("_test"):
            raise RuntimeError(
                "Live scenario tests may reset only the 'refund_operator' demo "
                "database or a database whose name ends with '_test'. Configured "
                f"database: '{database_name}'."
            )

    @contextmanager
    def connection(self) -> Iterator[MySQLConnectionAbstract]:
        database = self.settings.database
        connection = mysql.connector.connect(
            host=database.host,
            port=database.port,
            database=database.name,
            user=database.user,
            password=database.password,
            autocommit=False,
        )
        try:
            yield connection
        finally:
            if connection.is_connected():
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[MySQLConnectionAbstract]:
        with self.connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def reset_demo(self) -> None:
        """Reset only the six documented demo records/tables in one transaction."""
        eligible_purchase_date = datetime.now(timezone.utc).date() - timedelta(days=8)
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM gateway_transactions")
            cursor.execute("DELETE FROM refunds")
            cursor.execute("DELETE FROM agent_runs")
            cursor.execute(
                """
                UPDATE refund_policy
                SET refund_window_days = %s, auto_approval_limit = %s
                WHERE id = %s
                """,
                (30, 5000, 1),
            )
            cursor.execute(
                """
                UPDATE orders
                SET amount = %s, purchase_date = %s, status = %s,
                    refund_status = %s
                WHERE id = %s
                """,
                (7500, eligible_purchase_date, "DELIVERED", "NONE", "ORD456"),
            )
            cursor.execute(
                """
                UPDATE tickets
                SET order_id = %s, message = %s, status = %s
                WHERE id = %s
                """,
                ("ORD456", DEFAULT_TICKET_MESSAGE, "OPEN", "T123"),
            )

    def execute(self, query: str, parameters: tuple[Any, ...]) -> None:
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)

    def execute_statements(
        self,
        statements: tuple[tuple[str, tuple[Any, ...]], ...],
    ) -> None:
        with self.transaction() as connection, connection.cursor() as cursor:
            for query, parameters in statements:
                cursor.execute(query, parameters)

    def fetch_one(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        with self.connection() as connection, connection.cursor(
            dictionary=True
        ) as cursor:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
        assert row is not None, f"Expected one database row for query: {query}"
        return row

    def scalar(self, query: str, parameters: tuple[Any, ...] = ()) -> Any:
        row = self.fetch_one(query, parameters)
        return next(iter(row.values()))

    def agent_run(self, run_id: str) -> dict[str, Any]:
        return self.fetch_one(
            """
            SELECT id, ticket_id, order_id, intent, current_state,
                   policy_passed, approval_status, refund_id, idempotency_key,
                   last_observation, created_at, updated_at
            FROM agent_runs
            WHERE id = %s
            """,
            (run_id,),
        )

    def refund_count(self) -> int:
        return int(self.scalar("SELECT COUNT(*) AS record_count FROM refunds"))

    def agent_run_count(self) -> int:
        return int(self.scalar("SELECT COUNT(*) AS record_count FROM agent_runs"))

    def gateway_transaction_count(self) -> int:
        return int(
            self.scalar(
                "SELECT COUNT(*) AS record_count FROM gateway_transactions"
            )
        )

    def idempotency_key_transaction_count(self, idempotency_key: str) -> int:
        return int(
            self.scalar(
                """
                SELECT COUNT(*) AS record_count
                FROM gateway_transactions
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            )
        )

    def ticket_status(self) -> str:
        return str(
            self.scalar(
                "SELECT status FROM tickets WHERE id = %s",
                ("T123",),
            )
        )

    def order_refund_status(self) -> str:
        return str(
            self.scalar(
                "SELECT refund_status FROM orders WHERE id = %s",
                ("ORD456",),
            )
        )

    def run_cli(self, *arguments: str) -> CliResult:
        child_environment = os.environ.copy()
        child_environment["PYTHONIOENCODING"] = "utf-8"
        command = (
            [sys.executable, str(PROJECT_ROOT / "main.py")]
            if self.use_real_llm
            else [sys.executable, "-m", "scripts.run_scenario_cli"]
        )
        completed_process = subprocess.run(
            [*command, *arguments],
            cwd=PROJECT_ROOT,
            env=child_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.command_timeout_seconds,
            check=False,
        )
        return CliResult(
            arguments=arguments,
            return_code=completed_process.returncode,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
        )

    def start_ticket_and_get_run_id(self) -> tuple[str, CliResult]:
        result = self.run_cli("run-ticket", "T123")
        result.assert_succeeded()
        run_identifier_match = re.search(
            r"^Run:\s+(RUN_[A-Za-z0-9_]+)\s*$",
            result.stdout,
            flags=re.MULTILINE,
        )
        assert run_identifier_match is not None, (
            f"Could not find a run ID in CLI output:\n{result.stdout}"
        )
        return run_identifier_match.group(1), result


@pytest.fixture
def live_scenario() -> LiveScenarioHarness:
    """Provide the destructive live harness only when explicitly enabled."""
    if os.getenv(LIVE_SCENARIO_ENVIRONMENT_VARIABLE) != "1":
        pytest.skip(
            "Use python scripts/run_live_scenarios.py to run destructive scenarios."
        )
    return LiveScenarioHarness(load_settings())
