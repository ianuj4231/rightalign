"""Test-only CLI entry point with deterministic intent classification."""

from __future__ import annotations

import os
import sys

from app import orchestrator
from app.cli import main
from app.schemas.llm import IntentClassification


class DeterministicScenarioLLM:
    """Return constrained intent output without consuming an external API quota."""

    def classify_intent(self, customer_message: str) -> IntentClassification:
        normalized_message = customer_message.casefold()
        refund_requested = "refund" in normalized_message
        damaged_item = "damaged" in normalized_message
        prior_approval_claimed = "approved" in normalized_message
        return IntentClassification(
            intent="REFUND_REQUEST" if refund_requested else "UNKNOWN",
            reason="DAMAGED_ITEM" if damaged_item else None,
            customer_claims_prior_approval=prior_approval_claimed,
        )


def create_deterministic_scenario_llm(settings) -> DeterministicScenarioLLM:
    """Match the production factory call shape for test-only substitution."""
    del settings
    return DeterministicScenarioLLM()


if __name__ == "__main__":
    if os.getenv("RUN_LIVE_SCENARIO_TESTS") != "1":
        print(
            "Error: run_scenario_cli.py is reserved for the live scenario harness."
        )
        sys.exit(2)
    orchestrator.create_llm = create_deterministic_scenario_llm
    sys.exit(main())
