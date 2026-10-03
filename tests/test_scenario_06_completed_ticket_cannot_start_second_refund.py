"""Scenario 6: a completed ticket cannot start a duplicate refund."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_completed_ticket_cannot_start_second_refund(
    live_scenario: LiveScenarioHarness,
) -> None:
    assert live_scenario.settings.mock_gateway.simulate_timeout_after_commit is True
    live_scenario.reset_demo()
    run_id, _ = live_scenario.start_ticket_and_get_run_id()
    approval_result = live_scenario.run_cli("approve", run_id)
    approval_result.assert_succeeded()
    assert live_scenario.agent_run(run_id)["current_state"] == "COMPLETE"

    counts_before_second_attempt = (
        live_scenario.agent_run_count(),
        live_scenario.refund_count(),
        live_scenario.gateway_transaction_count(),
    )
    duplicate_attempt = live_scenario.run_cli("run-ticket", "T123")

    duplicate_attempt.assert_failed()
    assert "already RESOLVED" in duplicate_attempt.combined_output
    assert (
        live_scenario.agent_run_count(),
        live_scenario.refund_count(),
        live_scenario.gateway_transaction_count(),
    ) == counts_before_second_attempt
    assert live_scenario.idempotency_key_transaction_count("refund_ORD456") == 1
