"""Run live manual scenarios 2-10 separately and report a pass count."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_TEST_FILES = (
    "tests/test_scenario_02_customer_approval_claim_cannot_bypass_policy.py",
    "tests/test_scenario_03_restart_while_waiting_for_approval.py",
    "tests/test_scenario_04_trusted_rejection_blocks_execution.py",
    "tests/test_scenario_05_commit_then_timeout_recovers_exactly_once.py",
    "tests/test_scenario_06_completed_ticket_cannot_start_second_refund.py",
    "tests/test_scenario_07_customer_provided_amount_is_ignored.py",
    "tests/test_scenario_08_outside_policy_refund_fails_closed.py",
    "tests/test_scenario_09_auto_approved_boundary_amount.py",
    "tests/test_scenario_10_crash_recovery_with_gateway_success.py",
)


class LiveScenarioRunnerSettings(BaseModel):
    """Validated environment-controlled behavior for the standalone runner."""

    model_config = ConfigDict(extra="forbid")

    gap_seconds: float = Field(default=5.0, ge=0.0, le=300.0)
    use_real_llm: bool = False


def load_runner_settings() -> LiveScenarioRunnerSettings:
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        return LiveScenarioRunnerSettings.model_validate(
            {
                "gap_seconds": os.getenv("SCENARIO_TEST_GAP_SECONDS", "5"),
                "use_real_llm": os.getenv("SCENARIO_TEST_USE_REAL_LLM", "false"),
            }
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid live scenario runner configuration: {exc}") from exc


def main() -> int:
    settings = load_runner_settings()
    child_environment = os.environ.copy()
    child_environment["RUN_LIVE_SCENARIO_TESTS"] = "1"
    passed_scenarios: list[str] = []
    failed_scenarios: list[str] = []

    print("Running live MySQL/LLM scenarios 2 through 10.", flush=True)
    print(
        f"Gap between scenarios: {settings.gap_seconds:g} seconds.",
        flush=True,
    )
    print(
        "LLM mode: "
        + ("configured external provider" if settings.use_real_llm else "deterministic test client"),
        flush=True,
    )

    for scenario_index, scenario_file in enumerate(SCENARIO_TEST_FILES):
        scenario_number = scenario_index + 2
        print(f"\n===== Scenario {scenario_number}/10 =====", flush=True)
        completed_process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", scenario_file],
            cwd=PROJECT_ROOT,
            env=child_environment,
            check=False,
        )
        if completed_process.returncode == 0:
            passed_scenarios.append(scenario_file)
            print(f"Scenario {scenario_number}: PASSED", flush=True)
        else:
            failed_scenarios.append(scenario_file)
            print(f"Scenario {scenario_number}: FAILED", flush=True)

        if scenario_index < len(SCENARIO_TEST_FILES) - 1:
            time.sleep(settings.gap_seconds)

    print("\n===== LIVE SCENARIO SUMMARY =====", flush=True)
    print(
        f"Passed: {len(passed_scenarios)}/{len(SCENARIO_TEST_FILES)}",
        flush=True,
    )
    if failed_scenarios:
        print("Failed scenario files:", flush=True)
        for scenario_file in failed_scenarios:
            print(f"- {scenario_file}", flush=True)

    return 0 if not failed_scenarios else 1


if __name__ == "__main__":
    sys.exit(main())
