"""Channel system for inter-component communication within the framework."""

from framework.channels.base import Channel, Message, ChannelType
from framework.channels.normal import NormalChannel
from framework.channels.highspeed import HighSpeedChannel

__all__ = [
    "Channel",
    "ChannelType",
    "HighSpeedChannel",
    "Message",
    "NormalChannel",
]
