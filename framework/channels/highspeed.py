"""High-speed channel backed by an mmap ring buffer for low-latency communication."""

from __future__ import annotations

import logging
import mmap
import pickle
import struct
import threading
from typing import Optional

from framework.channels.base import Channel, ChannelType, Message

logger = logging.getLogger(__name__)

# Header layout: 4 bytes head (write index) + 4 bytes tail (read index) = 8 bytes total
_HEADER_SIZE = 8
# Struct format for a 4-byte unsigned little-endian integer
_UINT32_FMT = "<I"


class HighSpeedChannel(Channel):
    """Lock-free ring buffer channel using shared memory (mmap).

    Provides high-throughput, low-latency message passing via a pre-allocated
    ring buffer. Each slot stores a pickled Message with a 4-byte length prefix.

    Thread-safe via the GIL for single-slot operations; a minimal ``threading.Lock``
    protects multi-byte head/tail reads and struct writes.
    """

    def __init__(self, name: str, slot_count: int = 64, slot_size: int = 1024) -> None:
        """Initialize a HighSpeedChannel.

        Args:
            name: Human-readable channel name (used as mmap tag on some platforms).
            slot_count: Number of ring buffer slots (default 64).
            slot_size: Size in bytes per slot, including 4-byte length prefix (default 1024).
        """
        self._name = name
        self._slot_count = slot_count
        self._slot_size = slot_size
        self._data_size = slot_size - 4  # bytes available for payload per slot
        self._closed = False
        self._lock = threading.Lock()

        total_size = _HEADER_SIZE + (slot_count * slot_size)
        # Anonymous mmap: works on Windows with mmap.ACCESS_DEFAULT
        try:
            self._mmap = mmap.mmap(-1, total_size)
        except Exception:
            logger.exception("HighSpeedChannel: mmap allocation failed for %s", name)
            raise

        # Initialize head and tail to 0 (single-threaded init, lock not needed)
        self._write_uint32(0, 0)  # head at offset 0
        self._write_uint32(4, 0)  # tail at offset 4

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.HIGH_SPEED

    @property
    def size(self) -> int:
        """Return the number of messages currently in the buffer."""
        with self._lock:
            head = self._read_uint32(0)
            tail = self._read_uint32(4)
        if head >= tail:
            return head - tail
        return self._slot_count - (tail - head)

    def send(self, message: Message) -> bool:
        """Write a message into the next available ring buffer slot.

        Returns False if the buffer is full or the channel is closed.
        """
        if self._closed:
            return False

        try:
            payload = pickle.dumps(message)
        except (pickle.PickleError, Exception) as e:
            logger.warning("HighSpeedChannel: pickle failed on send: %s", e)
            return False

        if len(payload) > self._data_size:
            logger.warning(
                "HighSpeedChannel: payload too large (%d > %d bytes)",
                len(payload),
                self._data_size,
            )
            return False

        with self._lock:
            head = self._read_uint32(0)
            tail = self._read_uint32(4)

            next_head = (head + 1) % self._slot_count
            if next_head == tail:
                # Buffer full
                return False

            slot_offset = _HEADER_SIZE + (head * self._slot_size)

            # Write payload length (4 bytes) and payload atomically under lock
            try:
                struct.pack_into(_UINT32_FMT, self._mmap, slot_offset, len(payload))
                self._mmap[slot_offset + 4 : slot_offset + 4 + len(payload)] = payload
                # Advance head only after successful write
                self._write_uint32(0, next_head)
            except Exception:
                logger.exception(
                    "HighSpeedChannel: write failed to slot %d for channel %s",
                    head,
                    self._name,
                )
                return False

        return True

    def recv(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Read a message from the ring buffer tail.

        Returns None if the buffer is empty or the channel is closed.
        The ``timeout`` parameter is accepted for API compatibility but
        this implementation is non-blocking (poll-based).
        """
        if self._closed:
            return None

        with self._lock:
            head = self._read_uint32(0)
            tail = self._read_uint32(4)

            if head == tail:
                # Buffer empty
                return None

            slot_offset = _HEADER_SIZE + (tail * self._slot_size)

            # Read payload length and data with defensive error handling
            try:
                length = struct.unpack_from(_UINT32_FMT, self._mmap, slot_offset)[0]
            except Exception:
                logger.exception(
                    "HighSpeedChannel: failed to read slot header at tail %d for %s",
                    tail,
                    self._name,
                )
                return None

            if length > self._data_size:
                logger.warning(
                    "HighSpeedChannel: corrupt slot length %d at tail %d",
                    length,
                    tail,
                )
                return None

            try:
                payload_bytes = bytes(
                    self._mmap[slot_offset + 4 : slot_offset + 4 + length]
                )
            except Exception:
                logger.exception(
                    "HighSpeedChannel: failed to read payload at tail %d for %s",
                    tail,
                    self._name,
                )
                return None

            # Advance tail
            new_tail = (tail + 1) % self._slot_count
            try:
                self._write_uint32(4, new_tail)
            except Exception:
                logger.exception(
                    "HighSpeedChannel: failed to advance tail from %d to %d for %s",
                    tail,
                    new_tail,
                    self._name,
                )
                return None

        try:
            return pickle.loads(payload_bytes)
        except (pickle.UnpicklingError, Exception) as e:
            logger.warning("HighSpeedChannel: unpickle failed on recv: %s", e)
            return None

    def close(self) -> None:
        """Close the channel and unmap the shared memory."""
        if self._closed:
            return
        self._closed = True
        try:
            self._mmap.close()
        except Exception:
            logger.exception("HighSpeedChannel: error closing mmap for %s", self._name)

    def _read_uint32(self, offset: int) -> int:
        """Read a 4-byte unsigned integer from the mmap at the given offset.

        Must be called under ``self._lock``.
        """
        return struct.unpack_from(_UINT32_FMT, self._mmap, offset)[0]

    def _write_uint32(self, offset: int, value: int) -> None:
        """Write a 4-byte unsigned integer into the mmap at the given offset.

        Must be called under ``self._lock``.
        """
        struct.pack_into(_UINT32_FMT, self._mmap, offset, value)
