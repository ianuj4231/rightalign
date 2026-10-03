"""Scenario 10: restart verifies a committed gateway refund without reissuing."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_crash_recovery_with_gateway_success(
    live_scenario: LiveScenarioHarness,
) -> None:
    live_scenario.reset_demo()
    live_scenario.execute_statements(
        (
            (
                """
                INSERT INTO refunds (
                    id, order_id, amount, idempotency_key,
                    gateway_transaction_id, status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, NULL, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())
                """,
                (
                    "RF_CRASH_SUCCESS",
                    "ORD456",
                    7500,
                    "refund_ORD456",
                    "PENDING",
                ),
            ),
            (
                """
                INSERT INTO agent_runs (
                    id, ticket_id, order_id, intent, current_state,
                    policy_passed, approval_status, refund_id, idempotency_key,
                    last_observation, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, UTC_TIMESTAMP(), UTC_TIMESTAMP()
                )
                """,
                (
                    "RUN_CRASH_SUCCESS",
                    "T123",
                    "ORD456",
                    "REFUND_REQUEST",
                    "REFUND_EXECUTING",
                    True,
                    "APPROVED",
                    "RF_CRASH_SUCCESS",
                    "refund_ORD456",
                    "Simulated crash after gateway call",
                ),
            ),
            (
                """
                INSERT INTO gateway_transactions (
                    transaction_id, idempotency_key, order_id,
                    amount, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP())
                """,
                (
                    "GTX_CRASH_SUCCESS",
                    "refund_ORD456",
                    "ORD456",
                    7500,
                    "SUCCESS",
                ),
            ),
        )
    )

    resume_result = live_scenario.run_cli("resume", "RUN_CRASH_SUCCESS")

    resume_result.assert_succeeded()
    persisted_run = live_scenario.agent_run("RUN_CRASH_SUCCESS")
    persisted_refund = live_scenario.fetch_one(
        """
        SELECT gateway_transaction_id, status
        FROM refunds
        WHERE id = %s
        """,
        ("RF_CRASH_SUCCESS",),
    )
    assert "Checking gateway status instead of retrying refund" in (
        resume_result.combined_output
    )
    assert "[EXECUTE]" not in resume_result.combined_output
    assert persisted_run["current_state"] == "COMPLETE"
    assert persisted_refund["status"] == "SUCCESS"
    assert persisted_refund["gateway_transaction_id"] == "GTX_CRASH_SUCCESS"
    assert live_scenario.idempotency_key_transaction_count("refund_ORD456") == 1
    assert live_scenario.order_refund_status() == "REFUNDED"
    assert live_scenario.ticket_status() == "RESOLVED"
