"""Tests for CapabilityRegistry and capabilities/interests integration."""

import time
import unittest
from typing import Any

from framework.bus import MessageBus
from framework.capabilities import CapabilityRegistry
from framework.channels.base import Message
from framework.interfaces import BaseComponent


class TestCapabilityRegistry(unittest.TestCase):
    """Test CapabilityRegistry in isolation."""

    def test_register_and_invoke(self) -> None:
        reg = CapabilityRegistry()
        results: list[str] = []

        def handler(payload: Any) -> str:
            results.append(payload)
            return f"handled: {payload}"

        reg.register("test.cap", handler)
        result = reg.invoke("test.cap", "hello")
        self.assertEqual(result, ["handled: hello"])
        self.assertEqual(results, ["hello"])

    def test_no_provider_returns_empty(self) -> None:
        reg = CapabilityRegistry()
        result = reg.invoke("nonexistent", "data")
        self.assertEqual(result, [])

    def test_multiple_providers(self) -> None:
        reg = CapabilityRegistry()

        def h1(payload: Any) -> str:
            return f"h1: {payload}"

        def h2(payload: Any) -> str:
            return f"h2: {payload}"

        reg.register("multi", h1)
        reg.register("multi", h2)
        result = reg.invoke("multi", "x")
        self.assertEqual(len(result), 2)
        self.assertIn("h1: x", result)
        self.assertIn("h2: x", result)

    def test_handler_exception_does_not_break_others(self) -> None:
        reg = CapabilityRegistry()

        def bad_handler(payload: Any) -> str:
            raise ValueError("boom")

        def good_handler(payload: Any) -> str:
            return "ok"

        reg.register("err", bad_handler)
        reg.register("err", good_handler)
        result = reg.invoke("err", "data")
        # Only good_handler result should be present
        self.assertEqual(result, ["ok"])

    def test_unregister(self) -> None:
        reg = CapabilityRegistry()

        def handler(payload: Any) -> str:
            return "handled"

        reg.register("cap", handler)
        self.assertTrue(reg.has_provider("cap"))
        reg.unregister("cap", handler)
        self.assertFalse(reg.has_provider("cap"))
        self.assertEqual(reg.invoke("cap", "x"), [])

    def test_list_capabilities(self) -> None:
        reg = CapabilityRegistry()
        reg.register("a", lambda m: None)
        reg.register("b", lambda m: None)
        caps = reg.list_capabilities()
        self.assertEqual(set(caps), {"a", "b"})


class TestComponentCapabilities(unittest.TestCase):
    """Test that BaseComponent capabilities/interests work with MessageBus."""

    def test_capability_auto_registered_on_attach(self) -> None:
        class MyComponent(BaseComponent):
            name = "my_comp"
            capabilities = ["my.cap"]
            interests: list[str] = []

            def handle_message(self, message: Message) -> Any:
                return {"echo": message.payload}

        bus = MessageBus()
        comp = MyComponent()
        bus.register_component(comp)

        self.assertIn("my.cap", bus.list_capabilities())
        results = bus.invoke("my.cap", {"data": 42})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], {"echo": {"data": 42}})
        bus.shutdown()

    def test_interests_auto_subscribed_on_attach(self) -> None:
        received: list[Any] = []

        class MyComponent(BaseComponent):
            name = "listener"
            capabilities: list[str] = []
            interests = ["my.event"]

            def handle_message(self, message: Message) -> Any:
                received.append(message.payload)
                return None

        bus = MessageBus()
        comp = MyComponent()
        bus.register_component(comp)

        bus.emit("my.event", {"hello": "world"})
        time.sleep(0.1)
        bus.shutdown()

        self.assertEqual(received, [{"hello": "world"}])

    def test_detach_unregisters_capabilities(self) -> None:
        class MyComponent(BaseComponent):
            name = "temp_comp"
            capabilities = ["temp.cap"]
            interests: list[str] = []

            def handle_message(self, message: Message) -> Any:
                return None

        bus = MessageBus()
        comp = MyComponent()
        bus.register_component(comp)
        self.assertIn("temp.cap", bus.list_capabilities())

        bus.unregister_component("temp_comp")
        self.assertNotIn("temp.cap", bus.list_capabilities())
        bus.shutdown()

    def test_invoke_with_no_provider(self) -> None:
        bus = MessageBus()
        results = bus.invoke("nonexistent.cap", {"data": "x"})
        self.assertEqual(results, [])
        bus.shutdown()

    def test_emit_alias_for_publish(self) -> None:
        received: list[Any] = []

        bus = MessageBus()

        def handler(msg: Message) -> None:
            received.append(msg.payload)

        bus.subscribe("evt", handler)
        bus.emit("evt", {"test": True}, sender="test")
        time.sleep(0.1)
        bus.shutdown()

        self.assertEqual(received, [{"test": True}])


class TestLifecycleComponent(unittest.TestCase):
    """Test that existing LifecycleComponent from _test_helpers still works."""

    def test_lifecycle_component_with_interests(self) -> None:
        from framework._test_helpers import LifecycleComponent

        record: list[str] = []
        comp = LifecycleComponent(record=record, topic="lifecycle.test")
        bus = MessageBus()
        bus.register_component(comp)

        # LifecycleComponent subscribes to the given topic in on_start
        bus.emit("lifecycle.test", "payload")
        time.sleep(0.1)
        bus.shutdown()

        self.assertIn("started", record)
        self.assertIn("stopped", record)


if __name__ == "__main__":
    unittest.main()
