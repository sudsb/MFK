"""Capability registry: components expose capabilities, others invoke them.

Components register what they can do (capabilities). Other components
can invoke capabilities by name without knowing which component provides them.

Two modes are available:
- **Thread-safe (default)**: All methods are protected by an RLock, allowing
  concurrent register/unregister/invoke from multiple threads without data races.
- **Lock-free (thread_safe=False)**: Zero locking overhead. Use when you know
  only one module will call capabilities and registration happens in a single
  thread (e.g. during initialization). Provides maximum throughput.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional

log = logging.getLogger(__name__)


def _same_handler(h1: Callable[[Any], Any], h2: Callable[[Any], Any]) -> bool:
    """Compare two handlers, handling bound method identity issue.

    Python creates a new bound-method object on each attribute access,
    so ``obj.method is not obj.method``. We compare ``__func__`` and
    ``__self__`` for bound methods, fall back to identity for plain
    functions/lambdas.
    """
    s1 = getattr(h1, "__self__", None)
    s2 = getattr(h2, "__self__", None)
    if s1 is not None and s2 is not None:
        return s1 is s2 and getattr(h1, "__func__") is getattr(h2, "__func__")
    return h1 is h2


class CapabilityRegistry:
    """Maps capability names to provider components.

    Supports two modes via the ``thread_safe`` parameter:
    - ``thread_safe=True`` (default): Full RLock protection on all methods.
      Safe for concurrent access from multiple threads.
    - ``thread_safe=False``: No locking at all. Maximum performance for
      single-threaded or one-to-one module scenarios.

    Both modes share the same code path -- a ``_locked()`` context manager
    transparently acquires the lock when present, or becomes a no-op when
    ``thread_safe=False``.  No duplicated if/else branches.
    """

    def __init__(self, thread_safe: bool = True) -> None:
        self._registry: Dict[str, List[Callable[[Any], Any]]] = {}
        self._lock: Optional[threading.RLock] = (
            threading.RLock() if thread_safe else None
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Acquire the internal lock if it exists, otherwise do nothing.

        Usage:
            with self._locked():
                self._registry[name] = handler  # safe in both modes
        """
        if self._lock is not None:
            with self._lock:
                yield
        else:
            yield

    # -- Public API --

    def register(self, name: str, handler: Callable[[Any], Any]) -> None:
        """Register a capability. Multiple providers allowed (all will be called)."""
        with self._locked():
            self._registry.setdefault(name, []).append(handler)

    def unregister(self, name: str, handler: Callable[[Any], Any]) -> None:
        """Unregister a capability provider."""
        with self._locked():
            if name in self._registry:
                self._registry[name] = [
                    h for h in self._registry[name] if not _same_handler(h, handler)
                ]
                if not self._registry[name]:
                    del self._registry[name]

    def invoke(self, name: str, payload: Any) -> List[Any]:
        """Invoke a capability. Returns list of results from all providers.

        Returns empty list if no provider exists (by design -- callers
        should not care whether anyone handles the invocation).

        Thread-safe mode: takes a snapshot of handlers under lock, then
        invokes them outside the lock to avoid holding it during potentially
        long-running handler execution.

        Lock-free mode: reads handlers directly (single-thread guarantee).
        """
        with self._locked():
            handlers = list(self._registry.get(name, []))
        # Invoke outside the lock -- never block other threads during handler execution.
        results: List[Any] = []
        for handler in handlers:
            try:
                result = handler(payload)
                results.append(result)
            except Exception:
                log.exception("Capability '%s' handler failed", name)
        return results

    def has_provider(self, name: str) -> bool:
        """Check if any provider exists. Optional -- most callers shouldn't care."""
        with self._locked():
            return bool(self._registry.get(name))

    def list_capabilities(self) -> List[str]:
        """List all registered capability names."""
        with self._locked():
            return list(self._registry.keys())
