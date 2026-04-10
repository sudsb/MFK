"""Normal channel backed by a thread-safe or cross-process queue."""

from __future__ import annotations

import multiprocessing
import queue
from typing import Optional, Any

import logging

from framework.channels.base import Channel, ChannelType, Message

log = logging.getLogger(__name__)

# Picklable sentinel to signal channel closure. Use a unique bytes marker so it
# can safely be sent through multiprocessing.Queue.
_CLOSED_SENTINEL = b"__CHANNEL_CLOSED_V1__"


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

        # Use Any annotation to avoid strict generic type issues with typing
        if cross_process:
            self._queue: Any = multiprocessing.Queue(maxsize=maxsize)
        else:
            self._queue: Any = queue.Queue(maxsize=maxsize)

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.NORMAL

    def close(self) -> None:
        """Mark the channel closed and notify receivers.

        For cross-process queues we put a picklable sentinel value so child
        processes or other process consumers can observe closure. For
        in-process queues we do the same for uniformity.
        """
        if self._closed:
            return
        self._closed = True
        try:
            # Put sentinel; use non-blocking put to avoid deadlocks during shutdown
            # If queue is full, use put with timeout as a best-effort.
            try:
                self._queue.put(_CLOSED_SENTINEL, block=False)
            except Exception:
                # fallback: try a short blocking put
                self._queue.put(_CLOSED_SENTINEL, block=True, timeout=0.1)
        except Exception:
            # Ignore failures on close; channel is logically closed regardless
            pass

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
        try:
            if timeout is None:
                item = self._queue.get()
            elif timeout == 0:
                item = self._queue.get_nowait()
            else:
                item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        except (EOFError, OSError):
            # Multiprocessing queues may raise EOFError/OSError on closed pipes
            # Log and treat as empty/closed channel
            try:
                log.exception("NormalChannel.recv: queue read error for %s", self._name)
            except Exception:
                pass
            return None
        except Exception:
            try:
                log.exception("NormalChannel.recv: unexpected error for %s", self._name)
            except Exception:
                pass
            return None

        if item is _CLOSED_SENTINEL:
            self._closed = True
            return None

        if isinstance(item, Message):
            return item

        return None
