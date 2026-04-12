from __future__ import annotations

import asyncio
import importlib
import hashlib
import json
from collections import OrderedDict
import logging
import multiprocessing
import pickle
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Literal, Optional

from .channels.base import Message, ChannelType
from .channels.normal import NormalChannel
from .channels.highspeed import HighSpeedChannel
from .capabilities import CapabilityRegistry

log = logging.getLogger(__name__)

DeliveryMode = Literal["thread", "process", "asyncio"]


# ---------------------------------------------------------------------------
# Delivery Backends (Strategy Pattern)
# ---------------------------------------------------------------------------
class DeliveryBackend(ABC):
    @abstractmethod
    def dispatch(self, entry: Dict[str, Any], message: Message) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class ThreadBackend(DeliveryBackend):
    def __init__(self, max_workers: int) -> None:
        cpu_count = multiprocessing.cpu_count()
        workers = max_workers if max_workers > 0 else cpu_count
        self._thread_pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="bus-worker"
        )

    def dispatch(self, entry: Dict[str, Any], message: Message) -> None:
        handler = entry["handler"]
        self._thread_pool.submit(self._deliver_message, handler, message)

    @staticmethod
    def _deliver_message(handler: Callable[[Message], Any], message: Message) -> None:
        try:
            # If the handler is a bound method, check whether its instance
            # exposes a per-instance lock attribute and use it to serialize
            # handler invocation for that component. This helps components
            # that are not internally thread-safe to avoid concurrent
            # calls into the same instance when the ThreadBackend is used.
            bound_inst = getattr(handler, "__self__", None)
            if bound_inst is not None and hasattr(bound_inst, "_lock"):
                lock = getattr(bound_inst, "_lock")
                try:
                    with lock:
                        handler(message)
                except Exception:
                    log.exception(
                        "Error delivering message to handler (component-locked)"
                    )
            else:
                handler(message)
        except Exception:
            log.exception("Error delivering message to handler")

    def shutdown(self) -> None:
        self._thread_pool.shutdown(wait=True)


# Global cache for process backend to reuse component instances (worker-local).
# Use an LRU cache with a lock to avoid races if subprocess code uses threads.
_PROCESS_CACHE_MAX_ENTRIES = 64
_process_component_cache: "OrderedDict[str, Any]" = OrderedDict()
_process_cache_lock = threading.Lock()


def _process_dispatch(
    handler_info: Dict[str, Any], message_bytes: bytes
) -> Optional[Any]:
    try:
        message: Message = pickle.loads(message_bytes)

        # Cache key: module.class + deterministic hash of params to avoid
        # reusing instances with different constructor args.
        params = handler_info.get("params") or {}
        try:
            params_json = json.dumps(params, sort_keys=True, separators=(",", ":"))
        except TypeError:
            # Fallback: use repr if params not JSON-serializable
            params_json = repr(params)

        params_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()[:16]
        cache_key = (
            f"{handler_info['module']}.{handler_info['class_name']}@{params_hash}"
        )

        with _process_cache_lock:
            instance = _process_component_cache.get(cache_key)
            if instance is None:
                mod = importlib.import_module(handler_info["module"])
                cls = getattr(mod, handler_info["class_name"])
                instance = cls(**params)
                # Insert into ordered dict and evict if needed
                _process_component_cache[cache_key] = instance
                _process_component_cache.move_to_end(cache_key)
                if len(_process_component_cache) > _PROCESS_CACHE_MAX_ENTRIES:
                    # Pop the least-recently-used item
                    evicted_key, evicted_instance = _process_component_cache.popitem(
                        last=False
                    )
                    try:
                        # If the instance has a close/teardown, call it
                        if hasattr(evicted_instance, "detach_bus"):
                            evicted_instance.detach_bus()
                        elif hasattr(evicted_instance, "close"):
                            evicted_instance.close()
                    except Exception:
                        log.exception(
                            "Error tearing down evicted process-cached instance %s",
                            evicted_key,
                        )
            else:
                # mark as recently used
                _process_component_cache.move_to_end(cache_key)

        method = getattr(instance, handler_info["method_name"])
        return method(message)
    except Exception:
        # Log the full traceback and re-raise so multiprocessing.Pool
        # can surface the error to the parent's error_callback.
        log.exception(
            "Process handler dispatch failed for %s.%s",
            handler_info.get("module"),
            handler_info.get("class_name"),
        )
        raise


class ProcessBackend(DeliveryBackend):
    def __init__(self, max_workers: int) -> None:
        cpu_count = multiprocessing.cpu_count()
        workers = max_workers if max_workers > 0 else cpu_count
        self._process_pool = multiprocessing.Pool(processes=workers)
        # For fallback
        self._thread_fallback = ThreadBackend(max_workers)

    def dispatch(self, entry: Dict[str, Any], message: Message) -> None:
        handler_info: Optional[Dict[str, Any]] = entry.get("handler_info")

        if handler_info is None:
            log.warning(
                "Process delivery requires handler_info on subscribe; "
                "falling back to thread delivery"
            )
            self._thread_fallback.dispatch(entry, message)
            return

        message_bytes = pickle.dumps(message)
        try:
            self._process_pool.apply_async(
                _process_dispatch,
                args=(handler_info, message_bytes),
                error_callback=lambda e: log.exception("Process delivery error: %s", e),
            )
        except Exception as e:
            log.exception("Failed to submit to process pool: %s", e)

    def shutdown(self) -> None:
        self._thread_fallback.shutdown()
        # Attempt graceful shutdown first
        try:
            self._process_pool.close()
            self._process_pool.join()
        except Exception:
            log.exception("Process pool graceful close failed, forcing terminate")
            try:
                self._process_pool.terminate()
                self._process_pool.join()
            except Exception:
                log.exception("Process pool forced terminate failed")


class AsyncioBackend(DeliveryBackend):
    def __init__(self) -> None:
        self._event_loop = asyncio.new_event_loop()
        self._loop_started = threading.Event()
        self._loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._loop_thread.start()
        # Wait for the event loop to actually start (with timeout to avoid busy-wait)
        if not self._loop_started.wait(1):
            log.warning("AsyncioBackend: event loop did not start within timeout")

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._event_loop)
        # Signal that the loop has been set up
        try:
            self._loop_started.set()
        except Exception:
            log.exception("AsyncioBackend: failed to set loop started event")
        self._event_loop.run_forever()

    def dispatch(self, entry: Dict[str, Any], message: Message) -> None:
        if not self._event_loop.is_running():
            log.warning("AsyncioBackend: event loop not running; dropping message")
            return

        handler = entry["handler"]
        try:
            if asyncio.iscoroutinefunction(handler):
                asyncio.run_coroutine_threadsafe(handler(message), self._event_loop)
            else:
                self._event_loop.run_in_executor(
                    None, ThreadBackend._deliver_message, handler, message
                )
        except Exception:
            log.exception("AsyncioBackend: scheduling handler failed")

    def shutdown(self) -> None:
        try:
            if self._event_loop.is_running():
                # Cancel all pending tasks before stopping the loop
                def _cancel_and_stop() -> None:
                    pending = asyncio.all_tasks(self._event_loop)
                    for task in pending:
                        task.cancel()
                    # Schedule stop after cancellation
                    self._event_loop.call_later(0.1, self._event_loop.stop)

                self._event_loop.call_soon_threadsafe(_cancel_and_stop)
        except RuntimeError:
            pass
        self._loop_thread.join(timeout=10)
        try:
            if not self._event_loop.is_closed():
                self._event_loop.close()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------
class MessageBus:
    """Central message router with pluggable delivery backends.

    Supported ``delivery_mode`` values:
      - ``"thread"`` (default): handlers run in daemon threads via a
        ``ThreadPoolExecutor``.  Best for I/O-bound handlers.
      - ``"process"``: handlers run in a ``multiprocessing.Pool``.  Each
        handler call re-instantiates the target component in a child process,
        providing true isolation and CPU-bound safety.
      - ``"asyncio"``: handlers run on a shared event loop.  Coroutine
        handlers are awaited directly; synchronous handlers are dispatched
        via ``loop.run_in_executor``.

    The ``thread_safe`` parameter controls locking in internal registries:
      - ``True`` (default): Full thread-safety via RLock. Safe for concurrent
        multi-threaded access.
      - ``False``: No locking overhead. Use when only one module invokes
        capabilities and registration is single-threaded (max performance).
    """

    def __init__(
        self,
        default_channel: ChannelType = ChannelType.HIGH_SPEED,
        delivery_mode: DeliveryMode = "thread",
        max_workers: int = 0,
        thread_safe: bool = True,
    ) -> None:
        self._subscribers: Dict[str, List[Dict[str, Any]]] = {}
        self._channels: Dict[str, Any] = {}
        self._default_channel = default_channel
        self._delivery_mode: DeliveryMode = delivery_mode
        self._lock = threading.RLock()
        self._components: Dict[str, Any] = {}
        self._capabilities = CapabilityRegistry(thread_safe=thread_safe)

        # If configured for process delivery, ensure default channel is not HIGH_SPEED
        if (
            self._delivery_mode == "process"
            and self._default_channel == ChannelType.HIGH_SPEED
        ):
            log.warning(
                "MessageBus configured with delivery_mode='process' but default_channel=HIGH_SPEED; overriding default_channel to NORMAL for safety"
            )
            self._default_channel = ChannelType.NORMAL

        if delivery_mode == "thread":
            self._backend: DeliveryBackend = ThreadBackend(max_workers)
        elif delivery_mode == "process":
            self._backend = ProcessBackend(max_workers)
        elif delivery_mode == "asyncio":
            self._backend = AsyncioBackend()
        else:
            raise ValueError(f"Unknown delivery mode: {delivery_mode}")

    def shutdown(self) -> None:
        """Shutdown all channels, backends, and clear subscriptions."""
        # Shutdown sequence should: 1) detach components (so they can
        # unsubscribe and clean up), 2) shutdown delivery backend (wait
        # for in-flight deliveries), 3) close channels and clear subscriptions.

        # 1) Detach all components first so they can unsubscribe themselves
        # during their on_stop/detach_bus lifecycle.
        with self._lock:
            for component in list(self._components.values()):
                if hasattr(component, "detach_bus"):
                    try:
                        component.detach_bus()
                    except Exception:
                        log.exception("Error detaching component")
            self._components.clear()

        # 2) Shutdown backend (waits for executing handlers to complete).
        try:
            self._backend.shutdown()
        except Exception:
            log.exception("Error shutting down delivery backend")

        # 3) Clean up channels and subscriptions
        with self._lock:
            for channel in self._channels.values():
                if hasattr(channel, "close"):
                    try:
                        channel.close()
                    except Exception:
                        log.exception("Error closing channel")
            self._channels.clear()
            self._subscribers.clear()

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------
    def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], Any],
        channel_type: Optional[ChannelType] = None,
        handler_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "handler": handler,
            "handler_info": handler_info,
        }
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(entry)

        # Create channel metadata (double-check outside write-critical sections)
        self.get_channel(topic, channel_type or self._default_channel)

    def unsubscribe(self, topic: str, handler: Callable[[Message], Any]) -> None:
        with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic] = [
                    e for e in self._subscribers[topic] if e["handler"] is not handler
                ]

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish(
        self,
        topic: str,
        payload: Any,
        sender: str = "",
        channel_type: Optional[ChannelType] = None,
        ttl: int = 0,
    ) -> bool:
        # Create or fetch channel (does not block publish critically)
        channel = self.get_channel(topic, channel_type or self._default_channel)

        with self._lock:
            subs = self._subscribers.get(topic, None)
            if not subs:
                return False
            # Shallow copy the list for safe iteration outside the lock
            entries = list(subs)

        message = Message(
            topic=topic,
            payload=payload,
            sender=sender,
            channel_type=channel.channel_type,
            ttl=ttl,
        )

        for entry in entries:
            self._backend.dispatch(entry, message)

        return True

    # ------------------------------------------------------------------
    # Capability Management
    # ------------------------------------------------------------------
    def register_capability(self, name: str, handler: Callable) -> None:
        """Register a capability provided by a component."""
        self._capabilities.register(name, handler)

    def unregister_capability(self, name: str, handler: Callable) -> None:
        """Unregister a capability."""
        self._capabilities.unregister(name, handler)

    def invoke(self, capability: str, payload: Any = None) -> List[Any]:
        """Invoke a capability. Wraps payload in Message for handler compatibility.

        Returns results from all providers.
        Returns empty list if no provider -- caller should not care.
        """
        log.debug("Invoking capability '%s'", capability)
        # Wrap payload in a Message so handlers expecting Message objects work
        message = Message(
            topic=capability,
            payload=payload,
            sender="invoke",
            channel_type=ChannelType.NORMAL,
            ttl=0,
        )
        return self._capabilities.invoke(capability, message)

    def emit(self, topic: str, payload: Any = None, sender: str = "") -> bool:
        """Alias for publish -- emit an event to interested subscribers.

        Returns True if anyone received it, False otherwise.
        Caller should not care about the return value.
        """
        return self.publish(topic, payload, sender=sender)

    def list_capabilities(self) -> List[str]:
        """List all registered capability names."""
        return self._capabilities.list_capabilities()

    # ------------------------------------------------------------------
    # Component registration
    # ------------------------------------------------------------------
    def register_component(self, component: Any) -> None:
        """Register a component with the bus and call ``attach_bus``."""
        name = getattr(component, "name", str(id(component)))
        with self._lock:
            self._components[name] = component
        if hasattr(component, "attach_bus"):
            component.attach_bus(self)

    def unregister_component(self, name: str) -> None:
        """Unregister a component and call ``detach_bus``."""
        with self._lock:
            component = self._components.pop(name, None)
        if component and hasattr(component, "detach_bus"):
            try:
                component.detach_bus()
            except Exception:
                log.exception("Error detaching component '%s' during unregister", name)

    def get_channel(self, topic: str, channel_type: ChannelType) -> Any:
        """Get or create a channel for *topic*."""
        with self._lock:
            if topic not in self._channels:
                self._channels[topic] = self._create_channel(topic, channel_type)
            return self._channels[topic]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _create_channel(self, topic: str, channel_type: ChannelType) -> Any:
        if channel_type == ChannelType.HIGH_SPEED:
            # HighSpeedChannel is not cross-process safe. If the bus is
            # configured for process delivery, fall back to NormalChannel
            # and warn the user.
            if self._delivery_mode == "process":
                log.warning(
                    "HighSpeedChannel requested for topic %s but delivery_mode is 'process'; falling back to NormalChannel",
                    topic,
                )
                return NormalChannel(name=topic, cross_process=True)
            return HighSpeedChannel(name=topic)
        return NormalChannel(name=topic)
