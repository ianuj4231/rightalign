"""Scenario 2: untrusted customer approval cannot bypass trusted policy."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_customer_approval_claim_cannot_bypass_policy(
    live_scenario: LiveScenarioHarness,
) -> None:
    live_scenario.reset_demo()

    run_id, cli_result = live_scenario.start_ticket_and_get_run_id()

    persisted_run = live_scenario.agent_run(run_id)
    assert "Intent: REFUND_REQUEST" in cli_result.combined_output
    assert "Trust level: untrusted customer input" in cli_result.combined_output
    assert persisted_run["current_state"] == "WAITING_APPROVAL"
    assert persisted_run["policy_passed"] == 1
    assert persisted_run["approval_status"] == "PENDING"
    assert persisted_run["refund_id"] is None
    assert persisted_run["idempotency_key"] is None
    assert live_scenario.refund_count() == 0
    assert live_scenario.gateway_transaction_count() == 0
    assert live_scenario.ticket_status() == "OPEN"
