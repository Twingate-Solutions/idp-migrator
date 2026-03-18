"""structlog configuration for twingate-idp-migrator."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON output to stdout.

    Args:
        level: Logging level string (e.g. "DEBUG", "INFO", "WARNING").
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        A configured structlog BoundLogger.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
