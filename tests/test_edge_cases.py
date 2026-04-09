"""Edge case tests covering channels, pool, bus, registry, and backends."""

from __future__ import annotations

import threading
import time
import pickle
import asyncio
import logging

from framework.channels.normal import NormalChannel, _CLOSED_SENTINEL
from framework.pool import ObjectPool
from framework.bus import (
    MessageBus,
    ThreadBackend,
    ProcessBackend,
    AsyncioBackend,
    _process_dispatch,
    _process_component_cache,
    _PROCESS_CACHE_MAX_ENTRIES,
)
from framework.channels.base import Message, ChannelType
from framework.registry import ComponentRegistry
import test_exec

log = logging.getLogger("test_edge_cases")


def test_normal_channel_cross_process_sentinel() -> None:
    ch = NormalChannel("cross", cross_process=True)
    # send a message then close; recv should return the message then None
    msg = Message(topic="t", payload={"x": 1})
    assert ch.send(msg)
    ch.close()

    first = ch.recv(timeout=1)
    assert isinstance(first, Message)
    second = ch.recv(timeout=0.1)
    # sentinel observed -> None
    assert second is None


def test_object_pool_high_contention() -> None:
    created = []

    def factory():
        obj = object()
        created.append(obj)
        return obj

    pool = ObjectPool(factory=factory, max_size=2, name="contend")

    results = []

    def worker(i):
        try:
            inst = pool.acquire(timeout=0.2)
            time.sleep(0.05)
            pool.release(inst)
            results.append((i, True))
        except TimeoutError:
            results.append((i, False))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Pool should not have created more than max_size instances concurrently
    assert pool._total_created <= 2
    # Some threads should have succeeded
    assert any(ok for (_, ok) in results)
    # Under contention, at least one should time out
    assert any(not ok for (_, ok) in results)


def test_message_bus_shutdown_with_active_publishers() -> None:
    bus = MessageBus(delivery_mode="thread")

    def slow_handler(message: Message):
        time.sleep(0.2)

    bus.subscribe("busy", slow_handler)

    stop_event = threading.Event()

    def publisher():
        while not stop_event.is_set():
            bus.publish("busy", payload={"n": 1})
            time.sleep(0.01)

    t = threading.Thread(target=publisher)
    t.start()
    # let some messages be in flight
    time.sleep(0.05)
    # Calling shutdown while publishers active should return and not deadlock
    bus.shutdown()
    stop_event.set()
    t.join(timeout=1)
    assert not t.is_alive()


def test_process_backend_caching_and_fallback(monkeypatch) -> None:
    # Reduce cache max entries to trigger eviction deterministically
    monkeypatch.setattr("framework.bus._PROCESS_CACHE_MAX_ENTRIES", 2)

    # Create several distinct handler_info entries to populate cache
    handler_info = {
        "module": "test_exec",
        "class_name": "_DummyComponent",
        "method_name": "handle_message",
        "params": {},
    }

    msg = Message(topic="t", payload={})
    mb = Message(topic="t", payload={})
    msg_bytes = pickle.dumps(msg)

    # Run _process_dispatch multiple times to populate and evict
    _process_dispatch(handler_info, msg_bytes)
    _process_dispatch(handler_info, msg_bytes)
    # New params to create a different cache key
    handler_info2 = handler_info.copy()
    handler_info2["params"] = {"v": 1}
    _process_dispatch(handler_info2, msg_bytes)

    # Ensure cache size respects the reduced limit
    assert len(_process_component_cache) <= 2

    # Test ProcessBackend fallback when handler_info missing
    pb = ProcessBackend(max_workers=1)
    called = threading.Event()

    def local_handler(message: Message):
        called.set()

    entry = {"handler": local_handler, "handler_info": None}
    pb.dispatch(entry, msg)
    # give thread fallback time to run
    time.sleep(0.2)
    assert called.is_set()
    pb.shutdown()


def test_asyncio_backend_cancellation_and_shutdown() -> None:
    ab = AsyncioBackend()

    async def long_task(message: Message):
        # long sleep; shutdown should stop the loop
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            return

    entry = {"handler": long_task}
    ab.dispatch(entry, Message(topic="t", payload={}))
    # shutdown should stop the loop and join thread quickly
    ab.shutdown()


def test_highspeed_channel_with_process_delivery_mode() -> None:
    # If delivery_mode is process and default channel HIGH_SPEED, bus should
    # override default_channel to NORMAL and create NormalChannel for topics
    bus = MessageBus(default_channel=ChannelType.HIGH_SPEED, delivery_mode="process")
    ch = bus.get_channel("x", ChannelType.HIGH_SPEED)
    from framework.channels.normal import NormalChannel

    assert isinstance(ch, NormalChannel)
    bus.shutdown()


def test_registry_error_handling(tmp_path) -> None:
    reg = ComponentRegistry()
    # creating unknown component returns None without raising
    assert reg.create("nope") is None
    # register invalid class path
    reg.register_class("bad", "nonexistent.module.Class")
    assert reg.create("bad") is None


def test_component_lifecycle_complex_handlers() -> None:
    from framework.interfaces import BaseComponent

    class ComplexComponent(BaseComponent):
        name = "complex"

        def on_start(self) -> None:
            # subscribe to a topic on start
            if self._bus:
                self._bus.subscribe("c.topic", self.handle_message)

        def on_stop(self) -> None:
            # raise to ensure bus handles exceptions during detach
            raise RuntimeError("stop-fail")

        def handle_message(self, message: Message) -> None:
            return None

    bus = MessageBus()
    comp = ComplexComponent()
    # register_component should call attach_bus -> on_start and subscribe
    bus.register_component(comp)
    assert bus.publish("c.topic", payload={})
    # unregister_component should call detach_bus and swallow exception
    bus.unregister_component("complex")
    bus.shutdown()
