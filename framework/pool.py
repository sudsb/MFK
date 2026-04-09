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
        self,
        factory: Callable[[], Any],
        max_size: int = 10,
        name: str = "default",
        teardown: Callable[[Any], None] | None = None,
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._name = name
        self._pool: deque[Any] = deque()
        # Use a re-entrant lock so the same thread can notify while holding
        # the lock (the condition uses the same lock). This avoids deadlocks
        # when release() notifies waiters while still inside a locked section.
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._in_use: int = 0
        self._in_use_set: set[int] = set()
        self._total_created: int = 0
        self._teardown = teardown

    def acquire(self, timeout: float | None = None) -> Any:
        """Acquire an instance from the pool.

        If the pool can create a new instance (total_created < max_size), a new
        instance is created immediately. Otherwise waits up to ``timeout``
        seconds for an instance to be released. If timeout elapses, raises
        TimeoutError.
        """
        with self._cond:
            # If idle instance available, return it immediately
            if self._pool:
                instance = self._pool.popleft()
                self._in_use += 1
                self._in_use_set.add(id(instance))
                return instance

            # If we can create a new instance (pool growth allowed)
            current_total = self._total_created
            if self._max_size <= 0 or current_total < self._max_size:
                instance = self._factory()
                self._total_created += 1
                self._in_use += 1
                self._in_use_set.add(id(instance))
                return instance

            # Otherwise wait for release up to timeout
            waited = self._cond.wait(timeout=timeout)
            if not waited and not self._pool:
                raise TimeoutError(f"ObjectPool '{self._name}' acquire timed out")

            # We have been notified and should have an instance
            if self._pool:
                instance = self._pool.popleft()
                self._in_use += 1
                self._in_use_set.add(id(instance))
                return instance

            # Fallback: try to create one more if allowed
            if self._max_size <= 0 or self._total_created < self._max_size:
                instance = self._factory()
                self._total_created += 1
                self._in_use += 1
                self._in_use_set.add(id(instance))
                return instance

            raise TimeoutError(f"ObjectPool '{self._name}' acquire timed out")

    def release(self, instance: Any) -> None:
        if instance is None:
            return
        with self._lock:
            if id(instance) not in self._in_use_set:
                log.warning(
                    "Pool '%s': releasing instance that was not acquired from this pool",
                    self._name,
                )
                return
            self._in_use_set.remove(id(instance))
            self._in_use -= 1
            if self._max_size <= 0 or len(self._pool) < self._max_size:
                self._pool.append(instance)
                # Notify one waiter that an instance is available
                try:
                    with self._cond:
                        self._cond.notify(1)
                except Exception:
                    pass
            else:
                log.debug(
                    "Pool '%s': pool full (%d), discarding instance",
                    self._name,
                    self._max_size,
                )
                # Attempt to clean up the discarded instance if it exposes cleanup
                try:
                    if self._teardown:
                        self._teardown(instance)
                    elif hasattr(instance, "close"):
                        instance.close()
                    elif hasattr(instance, "shutdown"):
                        instance.shutdown()
                except Exception:
                    log.exception(
                        "Pool '%s': error during instance teardown", self._name
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
                inst = self._pool.pop()
                removed += 1
                try:
                    if self._teardown:
                        self._teardown(inst)
                    elif hasattr(inst, "close"):
                        inst.close()
                    elif hasattr(inst, "shutdown"):
                        inst.shutdown()
                except Exception:
                    log.exception("Pool '%s': error during shrink teardown", self._name)
        return removed

    def clear(self) -> None:
        with self._lock:
            # Clean up instances before clearing to avoid resource leaks
            while self._pool:
                inst = self._pool.pop()
                try:
                    if self._teardown:
                        self._teardown(inst)
                    elif hasattr(inst, "close"):
                        inst.close()
                    elif hasattr(inst, "shutdown"):
                        inst.shutdown()
                except Exception:
                    log.exception("Pool '%s': error during clear teardown", self._name)
