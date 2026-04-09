from __future__ import annotations
from typing import Any
import logging
from framework.interfaces import BaseComponent
from framework.channels.base import Message

log = logging.getLogger(__name__)


class ConsolePrinter(BaseComponent):
    """Subscribes to data events and prints content to console.

    Subscribes to 'data.loaded' topic.

    Params:
      - input_key: key in payload to print (default: 'file_content')
    """

    name: str = "console_printer"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.input_key: str = params.get("input_key", "file_content")

    def on_start(self) -> None:
        """Subscribe to data.loaded topic."""
        self._bus.subscribe("data.loaded", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        """Print the payload content."""
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
