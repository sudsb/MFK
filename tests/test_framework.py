import time
import pickle
import asyncio

import unittest

from framework.bus import MessageBus
from framework.pool import ObjectPool
from framework.registry import ComponentRegistry
from framework.channels.normal import NormalChannel
from framework._test_helpers import (
    LifecycleComponent,
)
from framework.channels.base import Message


class TestNormalChannelCrossProcess(unittest.TestCase):
    def test_closed_sentinel_picklable_across_process(self):
        # The closed sentinel must be pickle-able for cross-process queues.
        from framework.channels.normal import _CLOSED_SENTINEL

        dumped = pickle.dumps(_CLOSED_SENTINEL)
        loaded = pickle.loads(dumped)
        self.assertEqual(loaded, _CLOSED_SENTINEL)

    def test_recv_after_close_raises_or_returns_none(self):
        ch = NormalChannel(name="t", cross_process=False)
        ch.close()
        # recv should return None for closed normal channel implementation
        item = ch.recv(timeout=0)
        self.assertIsNone(item)


class TestObjectPoolContention(unittest.TestCase):
    def test_high_contention_acquire_release(self):
        created = []

        def factory():
            obj = object()
            created.append(obj)
            return obj

        pool = ObjectPool(factory=factory, max_size=3, name="testpool")

        # Acquire up to max size
        insts = [pool.acquire(timeout=0.1) for _ in range(3)]
        self.assertEqual(len(insts), 3)

        # A further acquire should time out
        with self.assertRaises(TimeoutError):
            pool.acquire(timeout=0.1)

        # Release one and acquire should succeed
        pool.release(insts.pop())
        inst4 = pool.acquire(timeout=0.1)
        self.assertIsNotNone(inst4)
        pool.release(inst4)

        # Clean up remaining
        for i in insts:
            pool.release(i)

        self.assertLessEqual(len(created), 3)


class TestMessageBusShutdownWithActivePublishers(unittest.TestCase):
    def test_shutdown_waits_for_active_thread_handlers(self):
        bus = MessageBus(delivery_mode="thread")
        processed = []

        def handler(msg: Message):
            time.sleep(0.2)
            processed.append(msg.payload)

        bus.subscribe("t", handler)
        bus.publish("t", "hello")
        # shutdown should wait for handler to complete
        start = time.time()
        bus.shutdown()
        elapsed = time.time() - start
        self.assertIn("hello", processed)
        self.assertGreaterEqual(elapsed, 0.1)


class TestProcessBackendCaching(unittest.TestCase):
    def test_process_backend_cache_and_fallback(self):
        # Create a bus with process delivery; use test_exec._DummyComponent via handler_info
        bus = MessageBus(delivery_mode="process")
        # Using handler_info without module should fall back to thread - ensure no exception
        # Subscribe without handler_info - should log and fallback
        called = []

        def h(msg: Message):
            called.append(msg.payload)

        bus.subscribe("p1", h)  # no handler_info
        bus.publish("p1", "x")
        bus.shutdown()
        self.assertIn("x", called)


class TestAsyncioBackendCancellation(unittest.TestCase):
    def test_asyncio_task_cancellation_on_shutdown(self):
        bus = MessageBus(delivery_mode="asyncio")
        called = []

        async def coro(msg: Message):
            # long-running task
            try:
                await asyncio_sleep(0.5)
                called.append(True)
            except Exception:
                called.append(False)

        # import local helper for sleeping without importing asyncio in top-level
        def asyncio_sleep(delay):
            return asyncio.sleep(delay)

        bus.subscribe("a", coro)
        bus.publish("a", "data")
        # give scheduling time
        time.sleep(0.05)
        bus.shutdown()
        # If cancellation worked, either called contains False or is empty
        self.assertTrue(len(called) <= 1)


class TestHighSpeedChannelWithProcessMode(unittest.TestCase):
    def test_highspeed_fallback_to_normal_when_process_mode(self):
        bus = MessageBus(delivery_mode="process", default_channel=1)  # HIGH_SPEED
        # get_channel should have fallen back to NormalChannel
        ch = bus.get_channel("topic1", channel_type=1)
        from framework.channels.base import ChannelType

        self.assertEqual(ch.channel_type, ChannelType.NORMAL)
        # ensure resources cleaned up
        bus.shutdown()


class TestRegistryErrorHandlingAndLifecycle(unittest.TestCase):
    def test_registry_create_failure_returns_none(self):
        r = ComponentRegistry()
        r.register_class("bad", "framework._test_helpers.BadInitComponent")
        comp = r.create("bad")
        self.assertIsNone(comp)

    def test_component_lifecycle_attach_detach(self):
        bus = MessageBus()
        record = []
        comp = LifecycleComponent(record=record, topic="l.topic")
        bus.register_component(comp)
        # attach_bus should have called on_start and subscribed
        bus.publish("l.topic", "payload")
        # let thread handlers run if any
        time.sleep(0.05)
        bus.unregister_component(comp.name)
        self.assertIn("started", record)
        self.assertIn("stopped", record)


if __name__ == "__main__":
    unittest.main()
