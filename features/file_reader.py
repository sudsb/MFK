from __future__ import annotations
from typing import Any
import logging
from framework.interfaces import BaseComponent
from framework.channels.base import Message

log = logging.getLogger(__name__)


class FileReader(BaseComponent):
    """Reads a file and publishes its content via the message bus.

    Subscribes to 'file.read' topic, publishes to 'data.loaded' topic.

    Params (via config.json):
      - path: path to the file (default: 'sample.txt')
      - output_key: key for the published data (default: 'file_content')
    """

    name: str = "file_reader"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.path: str = params.get("path", "sample.txt")
        self.output_key: str = params.get("output_key", "file_content")

    def on_start(self) -> None:
        """Subscribe to file.read topic."""
        self._bus.subscribe("file.read", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        """Read the file and return its content."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            error_msg = f"File not found: {self.path}"
            log.warning("FileReader: %s", error_msg)
            if self._bus:
                self._bus.publish(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}
        except OSError as e:
            error_msg = f"File read error: {self.path}: {e}"
            log.exception("FileReader: IO error reading %s", self.path)
            if self._bus:
                self._bus.publish(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error reading {self.path}: {e}"
            log.exception("FileReader: unexpected error reading %s", self.path)
            if self._bus:
                self._bus.publish(
                    "data.loaded",
                    payload={"error": error_msg},
                    sender=self.name,
                )
            return {"error": error_msg}

        # Publish the loaded data
        if self._bus:
            self._bus.publish(
                "data.loaded",
                payload={self.output_key: content},
                sender=self.name,
            )

        return {self.output_key: content}
