"""Scenario 4: a trusted rejection blocks refund execution permanently."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_trusted_rejection_blocks_execution(
    live_scenario: LiveScenarioHarness,
) -> None:
    live_scenario.reset_demo()
    run_id, _ = live_scenario.start_ticket_and_get_run_id()

    rejection_result = live_scenario.run_cli("reject", run_id)
    show_result = live_scenario.run_cli("show-run", run_id)

    rejection_result.assert_succeeded()
    show_result.assert_succeeded()
    rejected_run = live_scenario.agent_run(run_id)
    assert rejected_run["approval_status"] == "REJECTED"
    assert rejected_run["current_state"] == "NEEDS_HUMAN_REVIEW"
    assert "Approval: REJECTED" in show_result.combined_output
    assert "State: NEEDS_HUMAN_REVIEW" in show_result.combined_output
    assert live_scenario.ticket_status() == "OPEN"
    assert live_scenario.refund_count() == 0
    assert live_scenario.gateway_transaction_count() == 0

    run_count_before_invalid_approval = live_scenario.agent_run_count()
    invalid_approval_result = live_scenario.run_cli("approve", run_id)

    invalid_approval_result.assert_failed()
    assert "Cannot record approval" in invalid_approval_result.combined_output
    assert live_scenario.agent_run(run_id) == rejected_run
    assert live_scenario.agent_run_count() == run_count_before_invalid_approval
    assert live_scenario.refund_count() == 0
    assert live_scenario.gateway_transaction_count() == 0
