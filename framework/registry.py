from __future__ import annotations
from contextlib import contextmanager
import importlib
import logging
import threading
from typing import Any, Dict, Iterator, List, Optional
from .interfaces import BaseComponent

log = logging.getLogger(__name__)


class ComponentRegistry:
    """Manages component lifecycle: registration, instantiation, discovery.

    The framework does NOT know what components will connect in advance.
    Components are registered dynamically via class paths or direct instances.

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
        self._components: Dict[str, BaseComponent] = {}
        self._class_paths: Dict[str, str] = {}
        self._lock: Optional[threading.RLock] = (
            threading.RLock() if thread_safe else None
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Acquire the internal lock if it exists, otherwise do nothing.

        Usage:
            with self._locked():
                self._components[name] = component  # safe in both modes
        """
        if self._lock is not None:
            with self._lock:
                yield
        else:
            yield

    def register_instance(self, name: str, component: BaseComponent) -> None:
        """Register an existing component instance."""
        with self._locked():
            self._components[name] = component

    def register_class(self, name: str, class_path: str) -> None:
        """Register a component class by its module path (e.g. 'features.file_reader.FileReader')."""
        with self._locked():
            self._class_paths[name] = class_path

    def create(self, name: str, **params: Any) -> Optional[BaseComponent]:
        """Instantiate a registered component by name with given params."""
        with self._locked():
            class_path = self._class_paths.get(name)
        if not class_path:
            log.error("Component '%s' not registered", name)
            return None

        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            component = cls(**params)
            with self._locked():
                self._components[name] = component
            return component
        except Exception:
            log.exception("Failed to create component '%s' from '%s'", name, class_path)
            return None

    def get(self, name: str) -> Optional[BaseComponent]:
        """Get a registered component instance."""
        with self._locked():
            return self._components.get(name)

    def list_components(self) -> List[str]:
        """List all registered component names."""
        with self._locked():
            return list(self._components.keys())

    def unregister(self, name: str) -> None:
        """Unregister and cleanup a component."""
        with self._locked():
            component = self._components.pop(name, None)
        # Use detach_bus so the framework-run lifecycle is honored
        # (detach_bus calls on_stop and clears the bus reference).
        if component and hasattr(component, "detach_bus"):
            try:
                component.detach_bus()
            except Exception:
                log.exception("Error detaching component '%s'", name)

    def clear(self) -> None:
        """Remove all components."""
        with self._locked():
            names = list(self._components.keys())
            self._class_paths.clear()
        for name in names:
            self.unregister(name)
