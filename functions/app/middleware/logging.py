"""Centralized, safe server-side logging helpers.

This module is the single logging entry point for application code.  It keeps
Cloud Run logs searchable while avoiding request bodies and transcript content.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """Configure the process logger once at application startup."""
    level = logging.INFO if settings.is_production else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if settings.is_production else logging.INFO
    )


logger = logging.getLogger(settings.app_name)
logger.setLevel(logging.INFO)


def log_exception_group(*, event: str, exc: BaseException, **context: object) -> None:
    """Log every leaf exception in an ExceptionGroup with safe job context.

    ``TaskGroup`` wraps concurrent chunk failures in ``ExceptionGroup``.  A
    one-line type-only log hides the provider failure that triggered it; this
    helper preserves the exception type, message and traceback for each leaf.
    """
    leaves = exc.exceptions if isinstance(exc, BaseExceptionGroup) else (exc,)
    for item in leaves:
        if isinstance(item, BaseExceptionGroup):
            log_exception_group(event=event, exc=item, **context)
            continue
        fields = " ".join(f"{key}=%s" for key in context)
        values = tuple(context.values())
        logger.error(
            f"{event} {fields} error_type=%s error_message=%s",
            *values,
            type(item).__name__,
            str(item),
            exc_info=(type(item), item, item.__traceback__),
        )
