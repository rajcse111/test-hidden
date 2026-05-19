import sys
from pathlib import Path

from app.core.config import Settings
from loguru import logger


def configure_logging(settings: Settings) -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        serialize=False,
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        "logs/backend.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        serialize=True,
        enqueue=True,
    )
