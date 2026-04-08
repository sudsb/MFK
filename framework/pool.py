from __future__ import annotations
import threading
import logging
from typing import Any, Callable
from collections import deque

log = logging.getLogger(__name__)


class ObjectPool:
    """Manages reusable component instances to avoid create/destroy overhead.

    Components are acquired from the pool, used, then returned for reuse.
    The pool can grow up to a configurable max size.
    """

    def __init__(
        self, factory: Callable[[], Any], max_size: int = 10, name: str = "default"
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._name = name
        self._pool: deque = deque()
        self._lock = threading.Lock()
        self._in_use: int = 0

    def acquire(self) -> Any:
        with self._lock:
            if self._pool:
                instance = self._pool.popleft()
            else:
                instance = self._factory()
            self._in_use += 1
        return instance

    def release(self, instance: Any) -> None:
        if instance is None:
            return
        with self._lock:
            if self._in_use <= 0:
                log.warning(
                    "Pool '%s': releasing instance that was not acquired from this pool",
                    self._name,
                )
                return
            self._in_use -= 1
            if len(self._pool) < self._max_size:
                self._pool.append(instance)
            else:
                log.debug(
                    "Pool '%s': pool full (%d), discarding instance",
                    self._name,
                    self._max_size,
                )

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._pool) + self._in_use

    @property
    def idle_count(self) -> int:
        with self._lock:
            return len(self._pool)

    def shrink(self, target_size: int = 0) -> int:
        removed = 0
        with self._lock:
            while len(self._pool) > target_size:
                self._pool.pop()
                removed += 1
        return removed

    def clear(self) -> None:
        with self._lock:
            self._pool.clear()
