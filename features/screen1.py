"""Screen 1 component - integrates with framework's MessageBus."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
from framework.interfaces import BaseComponent

if TYPE_CHECKING:
    from framework.channels.base import Message


class Screen1(BaseComponent):
    """Screen 1 component. Registers with bus and participates in cross-screen communication."""

    name: str = "screen1"

    def on_start(self) -> None:
        self._bus.subscribe("ui.navigate_to_screen1", self.handle_message)
        self._bus.subscribe("ui.screen1_data", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        return {"received": message.topic, "payload": message.payload}
