"""Scenario 3: resuming a pending run stays safely paused."""

from tests.live_scenario_harness import LiveScenarioHarness


def test_restart_while_waiting_for_approval(
    live_scenario: LiveScenarioHarness,
) -> None:
    live_scenario.reset_demo()
    run_id, _ = live_scenario.start_ticket_and_get_run_id()
    run_before_resume = live_scenario.agent_run(run_id)

    resume_result = live_scenario.run_cli("resume", run_id)

    resume_result.assert_succeeded()
    run_after_resume = live_scenario.agent_run(run_id)
    assert "WAITING_APPROVAL" in resume_result.combined_output
    assert "[UNDERSTAND]" not in resume_result.combined_output
    assert run_after_resume == run_before_resume
    assert live_scenario.refund_count() == 0
    assert live_scenario.gateway_transaction_count() == 0
    assert live_scenario.ticket_status() == "OPEN"
