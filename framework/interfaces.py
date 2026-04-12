from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from .bus import MessageBus
    from .channels.base import Message


class BaseComponent(ABC):
    """A pluggable component that communicates via the MessageBus.

    Components register with the bus, subscribe to topics, and process messages.
    The framework does NOT know what components will connect in advance.

    Zero-coupling design:
    - capabilities: what this component can do (auto-registered on attach)
    - interests: what events this component cares about (auto-subscribed on attach)
    Components do NOT need to know about each other.
    """

    name: str = "unnamed"

    # === Declarative capabilities and interests ===
    # Capabilities this component provides (auto-registered to CapabilityRegistry)
    capabilities: List[str] = []
    # Events this component is interested in (auto-subscribed on attach)
    interests: List[str] = []

    def __init__(self, **params: Any) -> None:
        self.params: Dict[str, Any] = params
        self._bus: Optional[MessageBus] = None
        self._running = False
        # Per-component reentrant lock to help serialize handler calls when
        # the delivery backend invokes component methods from multiple threads.
        # Components that need finer-grained locking can provide their own locks.
        self._lock = threading.RLock()

    def attach_bus(self, bus: MessageBus) -> None:
        """Called by framework to give component access to the message bus.

        Automatically registers capabilities and subscribes to interests.
        """
        self._bus = bus
        self._running = True

        # Auto-register capabilities
        for cap in self.capabilities:
            bus.register_capability(cap, self.handle_message)

        # Auto-subscribe to interests
        for topic in self.interests:
            bus.subscribe(topic, self.handle_message)

        self.on_start()

    def detach_bus(self) -> None:
        """Called by framework to disconnect.

        Automatically unregisters capabilities and unsubscribes from interests.
        """
        self.on_stop()
        if self._bus:
            for cap in self.capabilities:
                self._bus.unregister_capability(cap, self.handle_message)
            for topic in self.interests:
                self._bus.unsubscribe(topic, self.handle_message)
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
