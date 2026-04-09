"""Edge case tests (unittest compatible) covering channels, pool, bus, registry, and backends."""

from __future__ import annotations

import threading
import time
import pickle
import asyncio
import logging
import unittest

from framework.channels.normal import NormalChannel
from framework.pool import ObjectPool
from framework.bus import (
    MessageBus,
    ProcessBackend,
    AsyncioBackend,
    _process_dispatch,
    _process_component_cache,
)
from framework.channels.base import Message, ChannelType
from framework.registry import ComponentRegistry

log = logging.getLogger("test_edge_cases")


class TestEdgeCases(unittest.TestCase):
    def test_normal_channel_cross_process_sentinel(self) -> None:
        ch = NormalChannel("cross", cross_process=True)
        msg = Message(topic="t", payload={"x": 1})
        self.assertTrue(ch.send(msg))
        ch.close()

        first = ch.recv(timeout=1)
        self.assertIsInstance(first, Message)
        second = ch.recv(timeout=0.1)
        self.assertIsNone(second)

    def test_object_pool_high_contention(self) -> None:
        created = []

        def factory():
            obj = object()
            created.append(obj)
            return obj

        pool = ObjectPool(factory=factory, max_size=2, name="contend")

        results = []

        def worker(i):
            try:
                inst = pool.acquire(timeout=0.01)
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

        self.assertLessEqual(pool._total_created, 2)
        self.assertTrue(any(ok for (_, ok) in results))
        self.assertTrue(any(not ok for (_, ok) in results))

    def test_message_bus_shutdown_with_active_publishers(self) -> None:
        bus = MessageBus(delivery_mode="thread")

        def slow_handler(message: Message):
            time.sleep(0.2)

        bus.subscribe("busy", slow_handler)

        stop_event = threading.Event()

        def publisher():
            while not stop_event.is_set():
                try:
                    bus.publish("busy", payload={"n": 1})
                except RuntimeError:
                    # backend may be shutting down; swallow and exit
                    break
                time.sleep(0.01)

        t = threading.Thread(target=publisher)
        t.start()
        time.sleep(0.05)
        bus.shutdown()
        stop_event.set()
        t.join(timeout=1)
        self.assertFalse(t.is_alive())

    def test_process_backend_caching_and_fallback(self) -> None:
        # Temporarily reduce cache size
        import framework.bus as busmod

        orig = getattr(busmod, "_PROCESS_CACHE_MAX_ENTRIES", None)
        try:
            setattr(busmod, "_PROCESS_CACHE_MAX_ENTRIES", 2)

            handler_info = {
                "module": "test_exec",
                "class_name": "_DummyComponent",
                "method_name": "handle_message",
                "params": {},
            }

            msg = Message(topic="t", payload={})
            msg_bytes = pickle.dumps(msg)

            _process_dispatch(handler_info, msg_bytes)
            _process_dispatch(handler_info, msg_bytes)
            handler_info2 = handler_info.copy()
            handler_info2["params"] = {"v": 1}
            _process_dispatch(handler_info2, msg_bytes)

            self.assertLessEqual(len(_process_component_cache), 2)

            pb = ProcessBackend(max_workers=1)
            called = threading.Event()

            def local_handler(message: Message):
                called.set()

            entry = {"handler": local_handler, "handler_info": None}
            pb.dispatch(entry, msg)
            time.sleep(0.2)
            self.assertTrue(called.is_set())
            pb.shutdown()
        finally:
            if orig is not None:
                setattr(busmod, "_PROCESS_CACHE_MAX_ENTRIES", orig)

    def test_asyncio_backend_cancellation_and_shutdown(self) -> None:
        ab = AsyncioBackend()

        async def long_task(message: Message):
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                return

        entry = {"handler": long_task}
        ab.dispatch(entry, Message(topic="t", payload={}))
        ab.shutdown()

    def test_highspeed_channel_with_process_delivery_mode(self) -> None:
        bus = MessageBus(
            default_channel=ChannelType.HIGH_SPEED, delivery_mode="process"
        )
        ch = bus.get_channel("x", ChannelType.HIGH_SPEED)
        from framework.channels.normal import NormalChannel

        self.assertIsInstance(ch, NormalChannel)
        bus.shutdown()

    def test_registry_error_handling(self) -> None:
        reg = ComponentRegistry()
        self.assertIsNone(reg.create("nope"))
        reg.register_class("bad", "nonexistent.module.Class")
        self.assertIsNone(reg.create("bad"))

    def test_component_lifecycle_complex_handlers(self) -> None:
        from framework.interfaces import BaseComponent

        class ComplexComponent(BaseComponent):
            name = "complex"

            def on_start(self) -> None:
                if self._bus:
                    self._bus.subscribe("c.topic", self.handle_message)

            def on_stop(self) -> None:
                raise RuntimeError("stop-fail")

            def handle_message(self, message: Message) -> None:
                return None

        bus = MessageBus()
        comp = ComplexComponent()
        bus.register_component(comp)
        self.assertTrue(bus.publish("c.topic", payload={}))
        bus.unregister_component("complex")
        bus.shutdown()


if __name__ == "__main__":
    unittest.main()
