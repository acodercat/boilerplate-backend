"""Logging through loguru.

Application code uses stdlib ``logging.getLogger(__name__)``; the loguru
sinks below (colored stderr, rotating files) receive those records through
:class:`InterceptHandler`.
"""

import inspect
import logging
import sys
from pathlib import Path
from types import FrameType

from loguru import logger

_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
_INTERCEPTED_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy")


class InterceptHandler(logging.Handler):
    """Forward stdlib ``logging`` records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk past the stdlib ``logging`` frames so ``{name}`` resolves to
        # the real caller rather than ``logging/__init__.py``.
        frame: FrameType | None = inspect.currentframe()
        depth = 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(*, log_dir: str, level: str) -> None:
    """Route all logging through loguru. Call once, before other app imports
    create their module-level loggers."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()

    logging.basicConfig(handlers=[InterceptHandler()], level=logging.NOTSET, force=True)
    for name in _INTERCEPTED_LOGGERS:
        named = logging.getLogger(name)
        named.handlers = [InterceptHandler()]
        # Otherwise each record is emitted twice: once here and again after
        # propagating to the root logger, which has the same interceptor.
        named.propagate = False

    # ``diagnose=False`` on every sink: loguru's default prints each frame's
    # local variables beside a traceback, and those include the passwords
    # and tokens a failing request was handling.
    logger.add(sys.stderr, level=level, format=_CONSOLE_FORMAT, diagnose=False)
    logger.add(
        f"{log_dir}/app.log",
        level=level,
        format=_FORMAT,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        diagnose=False,
    )
    logger.add(
        f"{log_dir}/error.log",
        level="ERROR",
        format=_FORMAT,
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        backtrace=True,
        diagnose=False,
    )
