from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .bus import MessageBus
    from .channels.base import Message


class BaseComponent(ABC):
    """A pluggable component that communicates via the MessageBus.

    Components register with the bus, subscribe to topics, and process messages.
    The framework does NOT know what components will connect in advance.
    """

    name: str = "unnamed"

    def __init__(self, **params: Any) -> None:
        self.params: Dict[str, Any] = params
        self._bus: Optional[MessageBus] = None
        self._running = False

    def attach_bus(self, bus: MessageBus) -> None:
        """Called by framework to give component access to the message bus."""
        self._bus = bus
        self._running = True

    def detach_bus(self) -> None:
        """Called by framework to disconnect."""
        self._running = False
        self._bus = None

    @abstractmethod
    def handle_message(self, message: Message) -> Any:
        """Process an incoming message. Return value is routed to subscribers."""

    def on_start(self) -> None:
        """Lifecycle hook: called when component is activated."""

    def on_stop(self) -> None:
        """Lifecycle hook: called when component is deactivated."""

    @property
    def is_running(self) -> bool:
        return self._running
