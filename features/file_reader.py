from __future__ import annotations
from typing import Any
import logging
from framework.interfaces import BaseComponent
from framework.channels.base import Message

log = logging.getLogger(__name__)


class FileReader(BaseComponent):
    """Reads a file and publishes its content via the message bus.

    Provides 'file.read' capability -- anyone can invoke it.
    Emits 'data.loaded' event when done -- anyone interested can listen.
    """

    name: str = "file_reader"

    # I provide this capability, I don't care who invokes it
    capabilities = ["file.read"]
    # I'm not interested in any events by default
    interests: list[str] = []

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.path: str = params.get("path", "sample.txt")
        self.output_key: str = params.get("output_key", "file_content")

    def handle_message(self, message: Message) -> Any:
        """Handle 'file.read' invocation."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            error_msg = f"File not found: {self.path}"
            log.warning("FileReader: %s", error_msg)
            if self._bus:
                self._bus.emit(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}
        except OSError as e:
            error_msg = f"File read error: {self.path}: {e}"
            log.exception("FileReader: IO error reading %s", self.path)
            if self._bus:
                self._bus.emit(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error reading {self.path}: {e}"
            log.exception("FileReader: unexpected error reading %s", self.path)
            if self._bus:
                self._bus.emit(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}

        # Emit the loaded data event -- whoever is interested will receive it
        if self._bus:
            self._bus.emit(
                "data.loaded",
                payload={self.output_key: content},
                sender=self.name,
            )

        return {self.output_key: content}
