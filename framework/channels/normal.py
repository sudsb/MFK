"""Normal channel backed by a thread-safe or cross-process queue."""

from __future__ import annotations

import multiprocessing
import queue
from typing import Optional

from framework.channels.base import Channel, ChannelType, Message

# Sentinel object to signal channel closure
_CLOSED_SENTINEL = object()


class NormalChannel(Channel):
    """Thread-safe channel using ``queue.Queue`` with optional cross-process support.

    When ``cross_process=False`` (default), uses ``queue.Queue`` for
    intra-process, thread-safe communication.

    When ``cross_process=True``, uses ``multiprocessing.Queue`` which
    serializes messages across process boundaries via pipes.
    """

    def __init__(
        self, name: str, maxsize: int = 0, cross_process: bool = False
    ) -> None:
        """Initialize a NormalChannel.

        Args:
            name: Human-readable channel name.
            maxsize: Maximum queue size (0 = unlimited).
            cross_process: If True, use multiprocessing.Queue for cross-process communication.
        """
        self._name = name
        self._maxsize = maxsize
        self._closed = False

        if cross_process:
            self._queue: queue.Queue[object] | multiprocessing.Queue = (
                multiprocessing.Queue(maxsize=maxsize)
            )
        else:
            self._queue: queue.Queue[object] | multiprocessing.Queue = queue.Queue(
                maxsize=maxsize
            )

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.NORMAL

    @property
    def size(self) -> int:
        try:
            return self._queue.qsize()
        except NotImplementedError:
            # multiprocessing.Queue.qsize() is not available on all platforms
            return -1

    def send(self, message: Message) -> bool:
        """Put a message into the queue.

        Returns False if the channel is closed or the queue is full
        (in non-blocking scenarios).
        """
        if self._closed:
            return False
        try:
            self._queue.put_nowait(message)
            return True
        except queue.Full:
            return False

    def recv(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Get a message from the queue with optional timeout.

        Returns None if the channel is closed, empty with timeout=0,
        or timeout expires while waiting.
        """
        if self._closed and self._queue.empty():
            return None

        try:
            if timeout is None:
                item = self._queue.get()
            elif timeout == 0:
                item = self._queue.get_nowait()
            else:
                item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        if item is _CLOSED_SENTINEL:
            self._closed = True
            return None

        if isinstance(item, Message):
            return item

        return None

    def close(self) -> None:
        """Mark the channel as closed and insert a sentinel for waiting receivers."""
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(_CLOSED_SENTINEL)
        except queue.Full:
            pass
