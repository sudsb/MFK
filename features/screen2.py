"""Screen 2 component - integrates with framework's MessageBus."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
from framework.interfaces import BaseComponent

if TYPE_CHECKING:
    from framework.channels.base import Message


class Screen2(BaseComponent):
    """Screen 2 component. Interested in navigation and data events."""

    name: str = "screen2"

    capabilities: list[str] = []
    interests = ["ui.navigate_to_screen2", "ui.screen2_data"]

    def handle_message(self, message: Message) -> Any:
        return {"received": message.topic, "payload": message.payload}
