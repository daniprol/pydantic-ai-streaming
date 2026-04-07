from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import EventDict, Processor
from structlog.typing import WrappedLogger

from streaming_chat_api.settings import Settings


def _drop_color_message(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict.pop('color_message', None)
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.StackInfoRenderer(),
        _drop_color_message,
    ]


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.logger_level.upper())

    logging.basicConfig(
        format='%(message)s',
        level=level,
        stream=sys.stdout,
        force=True,
    )

    processors = _shared_processors()
    renderer: Processor
    if settings.is_dev:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()
        processors = [*processors, structlog.processors.format_exc_info]

    structlog.configure(
        processors=[
            *processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processor=renderer,
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        handler.setLevel(level)

    for logger_name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'fastapi'):
        logging.getLogger(logger_name).setLevel(level)
