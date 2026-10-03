"""Consistent console logging for the CLI application."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
NOISY_LIBRARY_LOGGERS = ("google_genai", "httpx", "mysql.connector")


def configure_logging(level: int = logging.INFO) -> None:
    """Configure concise operational logs without changing CLI output calls."""
    logging.basicConfig(level=level, format=LOG_FORMAT)
    for logger_name in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
