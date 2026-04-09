"""Focused unit tests for MessageBus and channel error-handling behaviors.

These tests are isolated and rely only on the public framework API.
"""

from __future__ import annotations

import time
import asyncio
import logging
import unittest

from framework.bus import MessageBus
from framework.channels.base import ChannelType, Message
from framework.channels.normal import NormalChannel
from framework.registry import ComponentRegistry


logging.basicConfig(level=logging.DEBUG)


class TestErrorHandling(unittest.TestCase):
    def test_handler_exceptions_are_caught_thread(self):
        bus = MessageBus(delivery_mode="thread", max_workers=2)

        called = []

        def bad_handler(message: Message):
            raise RuntimeError("handler boom")

        def good_handler(message: Message):
            called.append(message.payload)

        bus.subscribe("topic.ex", bad_handler)
        bus.subscribe("topic.ex", good_handler)

        result = bus.publish("topic.ex", payload={"x": 1}, sender="t1")
        self.assertTrue(result)

        # allow background threads to run
        time.sleep(0.2)

        # good handler must have received the payload despite other handler raising
        self.assertEqual(called, [{"x": 1}])

        bus.shutdown()

    def test_process_pool_graceful_shutdown_and_fallback(self):
        # 1) fallback when handler_info missing
        bus = MessageBus(
            delivery_mode="process", default_channel=ChannelType.NORMAL, max_workers=2
        )

        called = []

        def record(message: Message):
            called.append(message.payload)

        # Subscribe without handler_info should fallback to thread delivery
        bus.subscribe("topic.proc", record)
        self.assertTrue(bus.publish("topic.proc", payload={"p": 1}))
        time.sleep(0.3)
        self.assertEqual(called, [{"p": 1}])

        # 2) subscribe with a process-style handler_info pointing to test_exec._DummyComponent
        # This verifies process dispatch path and that shutdown completes without raising
        bus.subscribe(
            "topic.proc",
            record,
            handler_info={
                "module": "test_exec",
                "class_name": "_DummyComponent",
                "method_name": "handle_message",
                "params": {},
            },
        )

        self.assertTrue(bus.publish("topic.proc", payload={"p": 2}))
        time.sleep(1.0)

        # Shutdown should finish gracefully (no exception)
        bus.shutdown()

    def test_asyncio_task_cancellation_during_shutdown(self):
        bus = MessageBus(delivery_mode="asyncio")

        started = []

        async def slow_handler(message: Message):
            started.append(True)
            # long sleep to simulate work that should be cancelled on shutdown
            await asyncio.sleep(2)

        bus.subscribe("topic.async", slow_handler)
        self.assertTrue(bus.publish("topic.async", payload={"a": 1}))

        # Wait until handler started
        time.sleep(0.1)

        t0 = time.monotonic()
        bus.shutdown()
        t1 = time.monotonic()

        # shutdown should not block for the full handler sleep time
        self.assertLess(t1 - t0, 2.0)

    def test_normal_channel_cross_process_close_behavior(self):
        ch = NormalChannel(name="ncross", cross_process=True)

        msg = Message(topic="t", payload={"v": 1})
        self.assertTrue(ch.send(msg))

        # Use a short blocking recv to accommodate multiprocessing.Queue timing
        r = ch.recv(timeout=1)
        # Should receive the same message
        self.assertIsNotNone(r)
        self.assertEqual(r.payload, {"v": 1})

        # Close the channel and ensure subsequent send/recv behave as closed
        ch.close()
        self.assertFalse(ch.send(Message(topic="t2", payload=None)))
        self.assertIsNone(ch.recv(timeout=0))

        # closing again is a no-op and must not raise
        ch.close()

    def test_highspeed_channel_in_process_mode_shutdown(self):
        # Ensure creating a bus with HIGH_SPEED + process mode and shutting down
        # completes without raising (HighSpeedChannel should be closed safely).
        bus = MessageBus(
            default_channel=ChannelType.HIGH_SPEED,
            delivery_mode="process",
            max_workers=1,
        )

        # handler_info points to test_exec._DummyComponent which simply logs
        bus.subscribe(
            "topic.hs",
            lambda m: None,
            handler_info={
                "module": "test_exec",
                "class_name": "_DummyComponent",
                "method_name": "handle_message",
                "params": {},
            },
        )

        self.assertTrue(bus.publish("topic.hs", payload={"hs": True}))
        time.sleep(0.5)
        bus.shutdown()

    def test_component_error_payloads_preserved(self):
        bus = MessageBus(delivery_mode="thread", max_workers=2)

        recorded = []

        def bad(message: Message):
            raise ValueError("boom")

        def rec(message: Message):
            recorded.append(message.payload)

        bus.subscribe("topic.err", bad)
        bus.subscribe("topic.err", rec)

        payload = {"keep": "me"}
        self.assertTrue(bus.publish("topic.err", payload=payload))
        time.sleep(0.2)

        # ensure the good handler received the original payload unchanged
        self.assertEqual(recorded, [payload])
        bus.shutdown()

    def test_registry_error_handling_for_creation_failures(self):
        registry = ComponentRegistry()

        # Invalid class path should return None and not raise
        registry.register_class("missing", "non.existent.ModuleClass")
        self.assertIsNone(registry.create("missing"))

        # Define a class in this test module that raises in __init__ and register it
        class Exploding:
            def __init__(self, **_):
                raise RuntimeError("init fail")

        # register using this module's import path so importlib can find it
        module_path = __name__ + ".Exploding"
        # ComponentRegistry expects a class path like 'module.ClassName'
        registry.register_class("boom", f"{__name__}.Exploding")

        # Attempt to create should return None and not raise
        self.assertIsNone(registry.create("boom"))


if __name__ == "__main__":
    unittest.main()
