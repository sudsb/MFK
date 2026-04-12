from __future__ import annotations
from typing import Any
import logging
from framework.interfaces import BaseComponent
from framework.channels.base import Message

log = logging.getLogger(__name__)


class ConsolePrinter(BaseComponent):
    """Subscribes to data events and prints content to console.

    Interested in 'data.loaded' events -- I don't care who emits them.
    """

    name: str = "console_printer"

    # I don't provide any capabilities
    capabilities: list[str] = []
    # I'm interested in this event, I don't care who emits it
    interests = ["data.loaded"]

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.input_key: str = params.get("input_key", "file_content")

    def handle_message(self, message: Message) -> Any:
        """Handle 'data.loaded' event."""
        try:
            if isinstance(message.payload, dict):
                value = message.payload.get(self.input_key, "")
            else:
                value = str(message.payload)

            print(value)
            return {"printed": value}
        except Exception:
            log.exception("ConsolePrinter: failed to handle message")
            return {"error": "print failed"}
