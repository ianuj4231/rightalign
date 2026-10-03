"""Command-line interface for the autonomous refund operator."""

import argparse
import logging

from app.config import load_settings
from app.exceptions import RefundOperatorError
from app.logging_config import configure_logging
from app.orchestrator import load_agent_run, run_agent, start_or_resume_ticket
from app.workflow.approval import approve_refund, reject_refund

logger = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous refund operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_ticket = subparsers.add_parser("run-ticket", help="Start or resume a ticket")
    run_ticket.add_argument("ticket_id")

    approve = subparsers.add_parser("approve", help="Approve a pending refund")
    approve.add_argument("run_id")

    reject = subparsers.add_parser("reject", help="Reject a pending refund")
    reject.add_argument("run_id")

    resume = subparsers.add_parser("resume", help="Resume a persisted workflow")
    resume.add_argument("run_id")

    show_run = subparsers.add_parser("show-run", help="Display durable run state")
    show_run.add_argument("run_id")
    return parser


def _show_agent_run(run_id: str) -> None:
    agent_run = load_agent_run(run_id)
    print(f"Run: {agent_run.id}")
    print(f"Ticket: {agent_run.ticket_id}")
    print(f"Order: {agent_run.order_id or '-'}")
    print(f"Intent: {agent_run.intent or '-'}")
    print(f"State: {agent_run.current_state.value}")
    print(
        "Approval: "
        f"{agent_run.approval_status.value if agent_run.approval_status else '-'}"
    )
    print(f"Refund: {agent_run.refund_id or '-'}")
    print(f"Idempotency key: {agent_run.idempotency_key or '-'}")
    print(f"Last observation: {agent_run.last_observation or '-'}")


def main(arguments: list[str] | None = None) -> int:
    configure_logging()
    parser = build_argument_parser()
    parsed_arguments = parser.parse_args(arguments)

    try:
        settings = load_settings()
        if parsed_arguments.command == "run-ticket":
            start_or_resume_ticket(parsed_arguments.ticket_id, settings=settings)
        elif parsed_arguments.command == "approve":
            approve_refund(parsed_arguments.run_id)
            run_agent(parsed_arguments.run_id, settings=settings)
        elif parsed_arguments.command == "reject":
            reject_refund(parsed_arguments.run_id)
        elif parsed_arguments.command == "resume":
            run_agent(parsed_arguments.run_id, settings=settings)
        elif parsed_arguments.command == "show-run":
            _show_agent_run(parsed_arguments.run_id)
        else:
            parser.error(f"Unsupported command: {parsed_arguments.command}")
    except RefundOperatorError as exc:
        logger.error(
            "CLI command failed safely: command=%s error_type=%s error=%s",
            parsed_arguments.command,
            type(exc).__name__,
            exc,
        )
        print(f"Error: {exc}")
        return 1
    return 0
