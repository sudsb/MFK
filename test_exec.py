"""Dummy component for process-mode delivery testing.

This module is kept free of other imports so the child process can
import it without side-effects.
"""

from __future__ import annotations

from framework.interfaces import BaseComponent
from framework.channels.base import Message
import logging

log = logging.getLogger("test_exec")


class _DummyComponent(BaseComponent):
    """Minimal component for process-mode testing."""

    name: str = "_dummy"

    def handle_message(self, message: Message) -> None:
        log.info(
            "[process-worker] received topic=%s payload=%s",
            message.topic,
            message.payload,
        )
