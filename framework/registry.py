from __future__ import annotations
import importlib
import logging
from typing import Any, Dict, List, Optional
from .interfaces import BaseComponent

log = logging.getLogger(__name__)


class ComponentRegistry:
    """Manages component lifecycle: registration, instantiation, discovery.

    The framework does NOT know what components will connect in advance.
    Components are registered dynamically via class paths or direct instances.
    """

    def __init__(self) -> None:
        self._components: Dict[str, BaseComponent] = {}
        self._class_paths: Dict[str, str] = {}

    def register_instance(self, name: str, component: BaseComponent) -> None:
        """Register an existing component instance."""
        self._components[name] = component

    def register_class(self, name: str, class_path: str) -> None:
        """Register a component class by its module path (e.g. 'features.file_reader.FileReader')."""
        self._class_paths[name] = class_path

    def create(self, name: str, **params: Any) -> Optional[BaseComponent]:
        """Instantiate a registered component by name with given params."""
        class_path = self._class_paths.get(name)
        if not class_path:
            log.error("Component '%s' not registered", name)
            return None

        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            component = cls(**params)
            self._components[name] = component
            return component
        except Exception:
            log.exception("Failed to create component '%s' from '%s'", name, class_path)
            return None

    def get(self, name: str) -> Optional[BaseComponent]:
        """Get a registered component instance."""
        return self._components.get(name)

    def list_components(self) -> List[str]:
        """List all registered component names."""
        return list(self._components.keys())

    def unregister(self, name: str) -> None:
        """Unregister and cleanup a component."""
        component = self._components.pop(name, None)
        if component and getattr(component, "is_running", False):
            try:
                component.on_stop()
            except Exception:
                log.exception("Error stopping component '%s'", name)

    def clear(self) -> None:
        """Remove all components."""
        for name in list(self._components.keys()):
            self.unregister(name)
        self._class_paths.clear()
