from __future__ import annotations

from framework.interfaces import BaseComponent
from framework.channels.base import Message


class BadInitComponent(BaseComponent):
    """Component whose constructor raises to test registry error handling."""

    def __init__(self, **params):
        # call super to satisfy LSP/typecheck, then fail to simulate bad init
        super().__init__(**params)
        raise RuntimeError("bad init")

    def handle_message(self, message: Message):
        raise RuntimeError("should not be called")


class LifecycleComponent(BaseComponent):
    """Component that records lifecycle events. Uses interests for auto-subscribe."""

    name: str = "lifecycle"

    capabilities: list[str] = []
    # Note: topic is set dynamically in __init__, interests updated there too
    interests: list[str] = []

    def __init__(self, record: list, topic: str = "test.topic", **params):
        super().__init__(**params)
        self.record = record
        self.topic = topic
        # Dynamically set interests based on topic
        self.interests = [topic]

    def on_start(self) -> None:
        self.record.append("started")

    def on_stop(self) -> None:
        self.record.append("stopped")

    def handle_message(self, message: Message) -> None:
        self.record.append(("msg", message.payload))
