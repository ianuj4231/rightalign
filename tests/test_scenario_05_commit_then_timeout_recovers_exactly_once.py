"""Scenario 5: commit-then-timeout recovers with one gateway transaction."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_commit_then_timeout_recovers_exactly_once(
    live_scenario: LiveScenarioHarness,
) -> None:
    assert live_scenario.settings.mock_gateway.simulate_timeout_after_commit is True, (
        "Scenario 5 requires mock_gateway.simulate_timeout_after_commit: true."
    )
    live_scenario.reset_demo()
    run_id, _ = live_scenario.start_ticket_and_get_run_id()

    approval_result = live_scenario.run_cli("approve", run_id)

    approval_result.assert_succeeded()
    completed_run = live_scenario.agent_run(run_id)
    refund = live_scenario.fetch_one(
        """
        SELECT id, order_id, amount, idempotency_key,
               gateway_transaction_id, status
        FROM refunds
        WHERE id = %s
        """,
        (completed_run["refund_id"],),
    )
    gateway_transaction = live_scenario.fetch_one(
        """
        SELECT transaction_id, idempotency_key, order_id, amount, status
        FROM gateway_transactions
        WHERE idempotency_key = %s
        """,
        ("refund_ORD456",),
    )

    assert "Request timed out" in approval_result.combined_output
    assert "Checking gateway status instead of retrying refund" in (
        approval_result.combined_output
    )
    assert completed_run["current_state"] == "COMPLETE"
    assert completed_run["policy_passed"] == 1
    assert completed_run["approval_status"] == "APPROVED"
    assert completed_run["idempotency_key"] == "refund_ORD456"
    assert refund["status"] == "SUCCESS"
    assert refund["amount"] == 7500
    assert refund["gateway_transaction_id"] == gateway_transaction["transaction_id"]
    assert gateway_transaction["amount"] == 7500
    assert gateway_transaction["status"] == "SUCCESS"
    assert live_scenario.order_refund_status() == "REFUNDED"
    assert live_scenario.ticket_status() == "RESOLVED"
    assert live_scenario.idempotency_key_transaction_count("refund_ORD456") == 1
