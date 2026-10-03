"""Scenario 8: an order outside the refund window fails closed."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_outside_policy_refund_fails_closed(
    live_scenario: LiveScenarioHarness,
) -> None:
    live_scenario.reset_demo()
    live_scenario.execute(
        """
        UPDATE orders
        SET purchase_date = DATE_SUB(UTC_DATE(), INTERVAL 31 DAY)
        WHERE id = %s
        """,
        ("ORD456",),
    )

    run_id, cli_result = live_scenario.start_ticket_and_get_run_id()

    persisted_run = live_scenario.agent_run(run_id)
    assert "Eligible: NO" in cli_result.combined_output
    assert persisted_run["current_state"] == "NEEDS_HUMAN_REVIEW"
    assert persisted_run["policy_passed"] == 0
    assert persisted_run["approval_status"] is None
    assert live_scenario.ticket_status() == "OPEN"
    assert live_scenario.refund_count() == 0
    assert live_scenario.gateway_transaction_count() == 0
