"""Scenario 9: the auto-approval boundary completes without human approval."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_auto_approved_boundary_amount(
    live_scenario: LiveScenarioHarness,
) -> None:
    assert live_scenario.settings.mock_gateway.simulate_timeout_after_commit is True
    live_scenario.reset_demo()
    live_scenario.execute(
        "UPDATE orders SET amount = %s WHERE id = %s",
        (5000, "ORD456"),
    )

    run_id, cli_result = live_scenario.start_ticket_and_get_run_id()

    persisted_run = live_scenario.agent_run(run_id)
    assert "Human approval required: NO" in cli_result.combined_output
    assert "WAITING_APPROVAL" not in cli_result.stdout
    assert persisted_run["approval_status"] == "NOT_REQUIRED"
    assert persisted_run["current_state"] == "COMPLETE"
    assert live_scenario.scalar(
        "SELECT amount FROM refunds WHERE order_id = %s",
        ("ORD456",),
    ) == 5000
    assert live_scenario.idempotency_key_transaction_count("refund_ORD456") == 1
    assert live_scenario.ticket_status() == "RESOLVED"
