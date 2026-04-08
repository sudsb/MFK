"""Base channel interface and message dataclass."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ChannelType(Enum):
    """Enumeration of available channel types."""

    NORMAL = "normal"
    HIGH_SPEED = "highspeed"


@dataclass
class Message:
    """Immutable message container for channel communication.

    Attributes:
        topic: Message topic/routing key.
        payload: Arbitrary payload data (must be picklable for cross-process).
        sender: Identifier of the message sender (empty if unspecified).
        timestamp: Monotonic timestamp at message creation.
        channel_type: Channel type this message was sent through.
        ttl: Time-to-live hop count; 0 means no limit.
    """

    topic: str
    payload: Any
    sender: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    channel_type: ChannelType = ChannelType.NORMAL
    ttl: int = 0  # 0 = no limit


class Channel(ABC):
    """Base interface for all communication channels.

    Implementations must provide thread-safe send/recv semantics,
    a close mechanism, and expose channel_type + size properties.
    """

    @abstractmethod
    def send(self, message: Message) -> bool:
        """Attempt to send a message through the channel.

        Args:
            message: The message to send.

        Returns:
            True if the message was successfully enqueued, False otherwise.
        """
        ...

    @abstractmethod
    def recv(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Receive a message from the channel.

        Args:
            timeout: Maximum seconds to wait. None means block indefinitely.
                     0 means non-blocking (return immediately if empty).

        Returns:
            The received Message, or None on timeout/channel closed.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the channel and release resources."""
        ...

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """Return the type of this channel."""
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """Return the current number of messages waiting to be received."""
        ...
