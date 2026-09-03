import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    level = logging.INFO if settings.is_production else logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Noisy third-party loggers, quieten in production
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if settings.is_production else logging.INFO
    )


logger = logging.getLogger(settings.app_name)