"""Screen 2 component - integrates with framework's MessageBus."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
from framework.interfaces import BaseComponent

if TYPE_CHECKING:
    from framework.channels.base import Message


class Screen2(BaseComponent):
    """Screen 2 component. Registers with bus and participates in cross-screen communication."""

    name: str = "screen2"

    def on_start(self) -> None:
        self._bus.subscribe("ui.navigate_to_screen2", self.handle_message)
        self._bus.subscribe("ui.screen2_data", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        return {"received": message.topic, "payload": message.payload}
