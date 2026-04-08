from __future__ import annotations

import asyncio
import importlib
import logging
import multiprocessing
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Literal, Optional

from .channels.base import Message, ChannelType
from .channels.normal import NormalChannel
from .channels.highspeed import HighSpeedChannel

log = logging.getLogger(__name__)

DeliveryMode = Literal["thread", "process", "asyncio"]


# ---------------------------------------------------------------------------
# Process-mode worker (top-level so it can be pickled)
# ---------------------------------------------------------------------------
def _process_dispatch(
    handler_info: Dict[str, Any], message_bytes: bytes
) -> Optional[Any]:
    """Reconstruct component in a child process and call its handler.

    ``handler_info`` contains:
      - module:   module path (e.g. ``"features.file_reader"``)
      - class_name: class name (e.g. ``"FileReader"``)
      - method_name: method to call (e.g. ``"handle_message"``)
      - params:    kwargs for ``__init__``
    """
    try:
        message: Message = pickle.loads(message_bytes)
        mod = importlib.import_module(handler_info["module"])
        cls = getattr(mod, handler_info["class_name"])
        instance = cls(**handler_info["params"])
        method = getattr(instance, handler_info["method_name"])
        return method(message)
    except Exception as e:
        log.exception("Process handler dispatch failed: %s", e)
        return None


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
    """

    def __init__(
        self,
        default_channel: ChannelType = ChannelType.HIGH_SPEED,
        delivery_mode: DeliveryMode = "thread",
        max_workers: int = 0,
    ) -> None:
        self._subscribers: Dict[str, List[Dict[str, Any]]] = {}
        self._channels: Dict[str, Any] = {}
        self._default_channel = default_channel
        self._delivery_mode: DeliveryMode = delivery_mode
        self._lock = threading.Lock()
        self._components: Dict[str, Any] = {}

        # Thread backend
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        # Process backend
        self._process_pool: Optional[multiprocessing.Pool] = None
        # Asyncio backend
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._init_backend(max_workers)

    # ------------------------------------------------------------------
    # Backend lifecycle
    # ------------------------------------------------------------------
    def _init_backend(self, max_workers: int) -> None:
        cpu_count = multiprocessing.cpu_count()
        workers = max_workers if max_workers > 0 else cpu_count

        if self._delivery_mode == "thread":
            self._thread_pool = ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="bus-worker"
            )
        elif self._delivery_mode == "process":
            self._process_pool = multiprocessing.Pool(
                processes=workers,
                initializer=self._process_init,
            )
        elif self._delivery_mode == "asyncio":
            self._event_loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._run_event_loop, daemon=True
            )
            self._loop_thread.start()

    @staticmethod
    def _process_init() -> None:
        """Initializer for child processes (no-op placeholder)."""
        pass

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._event_loop)  # type: ignore[arg-type]
        self._event_loop.run_forever()

    def shutdown(self) -> None:
        """Shutdown all channels, backends, and clear subscriptions."""
        with self._lock:
            for channel in self._channels.values():
                if hasattr(channel, "close"):
                    try:
                        channel.close()
                    except Exception:
                        log.exception("Error closing channel")
            self._channels.clear()
            self._subscribers.clear()
            for component in self._components.values():
                if hasattr(component, "detach_bus"):
                    try:
                        component.detach_bus()
                    except Exception:
                        log.exception("Error detaching component")
            self._components.clear()

        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None

        if self._process_pool:
            self._process_pool.terminate()
            self._process_pool.join()
            self._process_pool = None

        if self._event_loop and self._loop_thread:
            self._stop_event.set()
            try:
                if self._event_loop.is_running():
                    self._event_loop.call_soon_threadsafe(self._event_loop.stop)
            except RuntimeError:
                pass  # loop already closed
            self._loop_thread.join(timeout=5)
            try:
                if not self._event_loop.is_closed():
                    self._event_loop.close()
            except RuntimeError:
                pass
            self._event_loop = None
            self._loop_thread = None

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
        """Subscribe *handler* to *topic*.

        Parameters
        ----------
        topic : str
            Topic name.
        handler : callable
            Message handler.  Can be a regular function, bound method, or
            coroutine function (``async def``).
        channel_type : ChannelType | None
            Channel to use for this topic.  Falls back to the bus default.
        handler_info : dict | None
            For **process** delivery only: ``{"module": "...",
            "class_name": "...", "method_name": "...", "params": {...}}``.
            Used to re-instantiate the component in a child process.
            Optional for thread/asyncio modes.
        """
        entry: Dict[str, Any] = {
            "handler": handler,
            "handler_info": handler_info,
        }
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(entry)
            if topic not in self._channels:
                ch_type = channel_type or self._default_channel
                self._channels[topic] = self._create_channel(topic, ch_type)

    def unsubscribe(self, topic: str, handler: Callable[[Message], Any]) -> None:
        """Remove *handler* from *topic*."""
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
        """Publish a message to *topic* and deliver to all subscribers.

        Returns ``True`` if at least one subscriber was notified.
        """
        with self._lock:
            if topic not in self._channels:
                ch_type = channel_type or self._default_channel
                self._channels[topic] = self._create_channel(topic, ch_type)
            channel = self._channels[topic]
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            entries = list(self._subscribers[topic])

        if not entries:
            return False

        message = Message(
            topic=topic,
            payload=payload,
            sender=sender,
            channel_type=channel.channel_type,
            ttl=ttl,
        )

        channel.send(message)

        for entry in entries:
            self._dispatch(entry, message)

        return True

    # ------------------------------------------------------------------
    # Dispatch per backend
    # ------------------------------------------------------------------
    def _dispatch(self, entry: Dict[str, Any], message: Message) -> None:
        if self._delivery_mode == "thread":
            self._dispatch_thread(entry["handler"], message)
        elif self._delivery_mode == "process":
            self._dispatch_process(entry, message)
        elif self._delivery_mode == "asyncio":
            self._dispatch_asyncio(entry["handler"], message)

    def _dispatch_thread(
        self, handler: Callable[[Message], Any], message: Message
    ) -> None:
        if self._thread_pool is None:
            return
        self._thread_pool.submit(self._deliver_message, handler, message)

    def _dispatch_process(self, entry: Dict[str, Any], message: Message) -> None:
        handler_info: Optional[Dict[str, Any]] = entry.get("handler_info")
        handler: Callable[[Message], Any] = entry["handler"]

        if self._process_pool is None or handler_info is None:
            log.warning(
                "Process delivery requires handler_info on subscribe; "
                "falling back to thread delivery"
            )
            self._dispatch_thread(handler, message)
            return

        message_bytes = pickle.dumps(message)
        try:
            self._process_pool.apply_async(
                _process_dispatch,
                args=(handler_info, message_bytes),
                error_callback=lambda e: log.error(
                    "Process delivery error", exc_info=e
                ),
            )
        except Exception as e:
            log.exception("Failed to submit to process pool: %s", e)

    def _dispatch_asyncio(
        self, handler: Callable[[Message], Any], message: Message
    ) -> None:
        if self._event_loop is None or not self._event_loop.is_running():
            return

        if asyncio.iscoroutinefunction(handler):
            asyncio.run_coroutine_threadsafe(handler(message), self._event_loop)
        else:
            self._event_loop.run_in_executor(
                None, self._deliver_message, handler, message
            )

    # ------------------------------------------------------------------
    # Component registration
    # ------------------------------------------------------------------
    def register_component(self, component: Any) -> None:
        """Register a component with the bus and call ``attach_bus``."""
        name = getattr(component, "name", str(id(component)))
        self._components[name] = component
        if hasattr(component, "attach_bus"):
            component.attach_bus(self)

    def unregister_component(self, name: str) -> None:
        """Unregister a component and call ``detach_bus``."""
        component = self._components.pop(name, None)
        if component and hasattr(component, "detach_bus"):
            component.detach_bus()

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
            return HighSpeedChannel(name=topic)
        return NormalChannel(name=topic)

    @staticmethod
    def _deliver_message(handler: Callable[[Message], Any], message: Message) -> None:
        try:
            handler(message)
        except Exception:
            log.exception("Error delivering message to handler")
