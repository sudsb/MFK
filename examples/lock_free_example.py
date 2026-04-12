"""Lock-free mode example: maximum throughput for single-threaded scenarios.

When only one module invokes capabilities and registration happens in a single
thread (e.g. during initialization), you can disable locking for ~5-15% faster
registry operations.

Run from project root: python examples/lock_free_example.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
from framework.bus import MessageBus
from framework.registry import ComponentRegistry
from framework.capabilities import CapabilityRegistry
from framework.channels.base import Message, ChannelType
from framework.interfaces import BaseComponent

logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Example 1: Lock-free MessageBus for single-threaded pipeline
# ---------------------------------------------------------------------------


class DataProcessor(BaseComponent):
    """A simple processor that reads data and emits results."""

    name = "data_processor"
    capabilities = ["data.process"]
    interests = []

    def __init__(self, **params):
        super().__init__(**params)
        self.processed = 0

    def handle_message(self, message: Message):
        self.processed += 1
        payload = message.payload if isinstance(message.payload, dict) else {}
        result = {"processed": True, "input": payload.get("value", 0)}
        self._bus.emit("data.result", result, sender=self.name)
        return result


class ResultCollector(BaseComponent):
    """Collects processing results."""

    name = "result_collector"
    capabilities = []
    interests = ["data.result"]

    def __init__(self, **params):
        super().__init__(**params)
        self.results = []

    def handle_message(self, message: Message):
        self.results.append(message.payload)
        return {"collected": True}


def example_lock_free_bus():
    """Use thread_safe=False for a single-threaded config-driven pipeline."""
    print("=== Lock-free MessageBus (single-threaded pipeline) ===")

    # thread_safe=False disables all locking overhead
    bus = MessageBus(
        default_channel=ChannelType.NORMAL,
        delivery_mode="thread",
        thread_safe=False,  # <-- lock-free mode
    )

    processor = DataProcessor()
    collector = ResultCollector()

    bus.register_component(processor)
    bus.register_component(collector)

    # Invoke capabilities -- no lock contention
    for i in range(5):
        bus.invoke("data.process", {"value": i * 10})

    # Wait for async handlers
    time.sleep(0.1)

    print(f"  Processed: {processor.processed} items")
    print(f"  Collected: {len(collector.results)} results")

    bus.shutdown()
    print("  Done.\n")


# ---------------------------------------------------------------------------
# Example 2: Lock-free ComponentRegistry for fast initialization
# ---------------------------------------------------------------------------


def example_lock_free_registry():
    """Use thread_safe=False for fast single-threaded component loading."""
    print("=== Lock-free ComponentRegistry (fast init) ===")

    registry = ComponentRegistry(thread_safe=False)  # <-- lock-free

    # Register and create many components -- no lock overhead
    start = time.perf_counter()
    for i in range(200):
        registry.register_class(f"comp_{i}", "features.printer.ConsolePrinter")
        registry.create(f"comp_{i}")
    elapsed = time.perf_counter() - start

    print(f"  Registered + created 200 components in {elapsed * 1000:.2f}ms")
    print(f"  Total components: {len(registry.list_components())}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Direct CapabilityRegistry usage
# ---------------------------------------------------------------------------


def example_lock_free_capability():
    """Use thread_safe=False for direct capability management."""
    print("=== Lock-free CapabilityRegistry ===")

    registry = CapabilityRegistry(thread_safe=False)  # <-- lock-free

    # When calling registry.invoke directly, payload is passed as-is
    registry.register("math.double", lambda msg: msg * 2)
    registry.register("math.square", lambda msg: msg**2)

    results = registry.invoke("math.double", 21)
    print(f"  math.double(21) = {results}")

    results = registry.invoke("math.square", 7)
    print(f"  math.square(7) = {results}")
    print()


# ---------------------------------------------------------------------------
# Performance comparison
# ---------------------------------------------------------------------------


def benchmark_modes(iterations: int = 10_000):
    """Compare thread-safe vs lock-free performance."""
    print(f"=== Performance Comparison ({iterations} iterations) ===")

    for name, thread_safe in [("Thread-safe", True), ("Lock-free", False)]:
        registry = CapabilityRegistry(thread_safe=thread_safe)
        start = time.perf_counter()

        for i in range(iterations):
            cap = f"bench_{i % 100}"
            registry.register(cap, lambda m: i)
            registry.invoke(cap, {})
            registry.unregister(cap, lambda m: i)

        elapsed = time.perf_counter() - start
        print(f"  {name}: {elapsed:.4f}s")

    print()


if __name__ == "__main__":
    example_lock_free_bus()
    example_lock_free_registry()
    example_lock_free_capability()
    benchmark_modes(5_000)
