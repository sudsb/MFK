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
    """Component that subscribes on start and records lifecycle events."""

    name: str = "lifecycle"

    def __init__(self, record: list, topic: str = "test.topic", **params):
        super().__init__(**params)
        self.record = record
        self.topic = topic

    def on_start(self) -> None:
        # subscribe to a topic so we receive messages when attached
        if self._bus is not None:
            self._bus.subscribe(self.topic, self.handle_message)
        self.record.append("started")

    def on_stop(self) -> None:
        self.record.append("stopped")

    def handle_message(self, message: Message) -> None:
        self.record.append(("msg", message.payload))
