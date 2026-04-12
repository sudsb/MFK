"""Communication-based component framework.

Components plug into a MessageBus and communicate freely via channels.
The framework does NOT know what components will connect in advance.
"""

from .interfaces import BaseComponent
from .bus import MessageBus
from .registry import ComponentRegistry
from .capabilities import CapabilityRegistry
from .channels.base import Channel, Message, ChannelType
from .channels.normal import NormalChannel
from .channels.highspeed import HighSpeedChannel
from .pool import ObjectPool
from .cache import ParamCache
from .snapshot import SnapshotManager

__all__ = [
    # Core
    "BaseComponent",
    "MessageBus",
    "ComponentRegistry",
    "CapabilityRegistry",
    # Channels
    "Channel",
    "ChannelType",
    "Message",
    "NormalChannel",
    "HighSpeedChannel",
    # Performance
    "ObjectPool",
    "ParamCache",
    "SnapshotManager",
]
