"""Stress test for concurrent capability invocation and component registration.

Tests the thread-safety fixes applied to CapabilityRegistry and ComponentRegistry.
Runs multiple threads simultaneously invoking capabilities while concurrently
registering/unregistering components to verify no data races or exceptions occur.

Run with: python -m unittest tests.test_concurrency_stress
"""

import threading
import time
import unittest
from framework.capabilities import CapabilityRegistry
from framework.registry import ComponentRegistry


class DummyComponent:
    """Minimal component double for concurrency testing."""

    def __init__(self, **params):
        self.name = params.get("cmp_name", params.get("name", "dummy"))
        self.call_count = 0
        self._lock = threading.RLock()

    def handle_message(self, message):
        with self._lock:
            self.call_count += 1
        time.sleep(0.001)  # Simulate work
        return {"result": "ok", "component": self.name}


class TestCapabilityRegistryConcurrency(unittest.TestCase):
    """Test CapabilityRegistry under concurrent access."""

    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_concurrent_register_and_invoke(self):
        """Multiple threads register handlers while others invoke."""
        errors = []
        invoke_results = []
        barrier = threading.Barrier(10)  # 5 register + 5 invoke threads

        def register_handler(thread_id):
            barrier.wait()
            try:

                def handler(msg):
                    return f"handler_{thread_id}"

                self.registry.register(f"cap_{thread_id % 3}", handler)
            except Exception as e:
                errors.append(f"register error: {e}")

        def invoke_capability(thread_id):
            barrier.wait()
            try:
                results = self.registry.invoke(
                    f"cap_{thread_id % 3}", {"thread": thread_id}
                )
                invoke_results.append(len(results))
            except Exception as e:
                errors.append(f"invoke error: {e}")

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=register_handler, args=(i,)))
            threads.append(threading.Thread(target=invoke_capability, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Errors occurred: {errors}")
        self.assertTrue(len(invoke_results) > 0, "No invoke results collected")

    def test_concurrent_invoke_same_capability(self):
        """Multiple threads invoke the same capability simultaneously."""
        call_counts = {"count": 0}
        lock = threading.Lock()

        def shared_handler(msg):
            with lock:
                call_counts["count"] += 1
            return {"handled": True}

        self.registry.register("shared.cap", shared_handler)

        num_threads = 20
        invoke_count = 50
        errors = []
        total_results = []

        def invoke_many():
            try:
                for _ in range(invoke_count):
                    results = self.registry.invoke("shared.cap", {})
                    total_results.extend(results)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=invoke_many) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent invoke errors: {errors}")
        expected = num_threads * invoke_count
        self.assertEqual(
            call_counts["count"],
            expected,
            f"Expected {expected} calls, got {call_counts['count']}",
        )
        self.assertEqual(len(total_results), expected, "Missing results")

    def test_concurrent_register_unregister_invoke(self):
        """Stress test: register, unregister, and invoke all happening at once."""
        errors = []
        ops_completed = {"register": 0, "unregister": 0, "invoke": 0}
        ops_lock = threading.Lock()
        barrier = threading.Barrier(15)

        def stress_register(thread_id):
            barrier.wait()
            for i in range(100):
                try:

                    def handler(msg):
                        return f"r{thread_id}_{i}"

                    self.registry.register(f"cap_{i % 10}", handler)
                    with ops_lock:
                        ops_completed["register"] += 1
                except Exception as e:
                    errors.append(f"register: {e}")

        def stress_unregister(thread_id):
            barrier.wait()
            for i in range(100):
                try:

                    def handler(msg):
                        return f"r{thread_id}_{i}"

                    self.registry.unregister(f"cap_{i % 10}", handler)
                    with ops_lock:
                        ops_completed["unregister"] += 1
                except Exception as e:
                    errors.append(f"unregister: {e}")

        def stress_invoke(thread_id):
            barrier.wait()
            for i in range(100):
                try:
                    _ = self.registry.invoke(f"cap_{i % 10}", {"t": thread_id})
                    with ops_lock:
                        ops_completed["invoke"] += 1
                except Exception as e:
                    errors.append(f"invoke: {e}")

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=stress_register, args=(i,)))
            threads.append(threading.Thread(target=stress_unregister, args=(i,)))
            threads.append(threading.Thread(target=stress_invoke, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Stress test errors: {errors}")
        self.assertEqual(ops_completed["register"], 500)
        self.assertEqual(ops_completed["unregister"], 500)
        self.assertEqual(ops_completed["invoke"], 500)

    def test_has_provider_and_list_concurrent(self):
        """has_provider and list_capabilities under concurrent modification."""
        errors = []

        def modify():
            try:
                for i in range(200):

                    def handler(msg):
                        return "ok"

                    self.registry.register(f"cap_{i % 20}", handler)
                    if i % 2 == 0:

                        def handler2(msg):
                            return "ok2"

                        self.registry.unregister(f"cap_{i % 20}", handler2)
            except Exception as e:
                errors.append(f"modify: {e}")

        def query():
            try:
                for _ in range(200):
                    _ = self.registry.has_provider("cap_5")
                    _ = self.registry.list_capabilities()
            except Exception as e:
                errors.append(f"query: {e}")

        t1 = threading.Thread(target=modify)
        t2 = threading.Thread(target=query)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Concurrent query errors: {errors}")


class TestComponentRegistryConcurrency(unittest.TestCase):
    """Test ComponentRegistry under concurrent access."""

    def setUp(self):
        self.registry = ComponentRegistry()

    def test_concurrent_register_and_create(self):
        """Multiple threads register classes and create components."""
        errors = []
        created = []
        barrier = threading.Barrier(10)

        # Pre-register some classes
        for i in range(5):
            self.registry.register_class(
                f"comp_{i}", "tests.test_concurrency_stress.DummyComponent"
            )

        def register_more(thread_id):
            barrier.wait()
            try:
                self.registry.register_class(
                    f"extra_{thread_id}", "tests.test_concurrency_stress.DummyComponent"
                )
            except Exception as e:
                errors.append(f"register error: {e}")

        def create_component(thread_id):
            barrier.wait()
            try:
                comp = self.registry.create(
                    f"comp_{thread_id % 5}", cmp_name=f"comp_{thread_id}"
                )
                if comp is not None:
                    created.append(comp)
            except Exception as e:
                errors.append(f"create error: {e}")

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=register_more, args=(i,)))
            threads.append(threading.Thread(target=create_component, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Errors occurred: {errors}")
        self.assertEqual(
            len(created), 5, f"Expected 5 created components, got {len(created)}"
        )

    def test_concurrent_create_get_unregister(self):
        """Stress test: create, get, and unregister simultaneously."""
        errors = []
        ops_completed = {"create": 0, "get": 0, "unregister": 0}
        ops_lock = threading.Lock()

        # Pre-register
        for i in range(10):
            self.registry.register_class(
                f"comp_{i}", "tests.test_concurrency_stress.DummyComponent"
            )

        def stress_create(thread_id):
            for i in range(50):
                try:
                    comp = self.registry.create(
                        f"comp_{(thread_id + i) % 10}",
                        cmp_name=f"dynamic_{thread_id}_{i}",
                    )
                    if comp:
                        with ops_lock:
                            ops_completed["create"] += 1
                except Exception as e:
                    errors.append(f"create: {e}")

        def stress_get(thread_id):
            for i in range(50):
                try:
                    _ = self.registry.get(f"comp_{i % 10}")
                    with ops_lock:
                        ops_completed["get"] += 1
                except Exception as e:
                    errors.append(f"get: {e}")

        def stress_unregister(thread_id):
            for i in range(50):
                try:
                    self.registry.unregister(f"comp_{(thread_id + i) % 10}")
                    with ops_lock:
                        ops_completed["unregister"] += 1
                except Exception as e:
                    errors.append(f"unregister: {e}")

        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=stress_create, args=(i,)))
            threads.append(threading.Thread(target=stress_get, args=(i,)))
            threads.append(threading.Thread(target=stress_unregister, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Stress test errors: {errors}")
        self.assertEqual(
            ops_completed["create"]
            + ops_completed["get"]
            + ops_completed["unregister"],
            450,
        )

    def test_concurrent_list_components(self):
        """list_components under concurrent modification."""
        errors = []

        def modify():
            try:
                for i in range(100):
                    self.registry.register_class(
                        f"comp_{i % 20}", "tests.test_concurrency_stress.DummyComponent"
                    )
                    if i % 3 == 0:
                        self.registry.unregister(f"comp_{i % 20}")
            except Exception as e:
                errors.append(f"modify: {e}")

        def query():
            try:
                for _ in range(100):
                    _ = self.registry.list_components()
            except Exception as e:
                errors.append(f"query: {e}")

        t1 = threading.Thread(target=modify)
        t2 = threading.Thread(target=query)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Concurrent list errors: {errors}")

    def test_clear_concurrent(self):
        """clear() while other threads are accessing."""
        errors = []

        # Populate
        for i in range(20):
            self.registry.register_class(
                f"comp_{i}", "tests.test_concurrency_stress.DummyComponent"
            )
            self.registry.create(f"comp_{i}", cmp_name=f"comp_{i}")

        def modify():
            try:
                for i in range(50):
                    self.registry.register_class(
                        f"extra_{i}", "tests.test_concurrency_stress.DummyComponent"
                    )
                    self.registry.create(f"extra_{i}", cmp_name=f"extra_{i}")
                    if i % 5 == 0:
                        self.registry.unregister(f"comp_{i % 20}")
            except Exception as e:
                errors.append(f"modify: {e}")

        def clear_all():
            try:
                time.sleep(0.01)  # Let modify start
                self.registry.clear()
            except Exception as e:
                errors.append(f"clear: {e}")

        def query():
            try:
                for _ in range(50):
                    _ = self.registry.list_components()
                    _ = self.registry.get("comp_5")
            except Exception as e:
                errors.append(f"query: {e}")

        threads = [
            threading.Thread(target=modify),
            threading.Thread(target=clear_all),
            threading.Thread(target=query),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Clear concurrent errors: {errors}")


class TestMessageBusIntegration(unittest.TestCase):
    """Integration test: MessageBus with concurrent invoke/emit."""

    def test_concurrent_invoke_through_bus(self):
        """Multiple threads invoke capabilities through MessageBus."""
        from framework.bus import MessageBus
        from framework.interfaces import BaseComponent
        from framework.channels.base import Message

        class TestProvider(BaseComponent):
            name = "test_provider"
            capabilities = ["test.cap"]
            interests = []

            def __init__(self, **params):
                super().__init__(**params)
                self.call_count = 0

            def handle_message(self, message: Message):
                with self._lock:
                    self.call_count += 1
                return {"handled": True}

        bus = MessageBus()
        provider = TestProvider()
        bus.register_capability("test.cap", provider.handle_message)

        errors = []
        total_results = []
        results_lock = threading.Lock()

        def invoke_many():
            try:
                for _ in range(100):
                    results = bus.invoke("test.cap", {})
                    with results_lock:
                        total_results.extend(results)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=invoke_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Bus invoke errors: {errors}")
        self.assertEqual(
            len(total_results), 1000, f"Expected 1000 results, got {len(total_results)}"
        )
        self.assertEqual(
            provider.call_count, 1000, f"Provider called {provider.call_count} times"
        )

        bus.shutdown()


class TestLockFreeModeCorrectness(unittest.TestCase):
    """Verify lock-free mode works correctly in single-threaded scenarios."""

    def test_capability_registry_lock_free_basic(self):
        """Lock-free registry works for single-threaded register/invoke."""
        registry = CapabilityRegistry(thread_safe=False)
        self.assertIsNone(registry._lock)

        results = []

        def handler(msg):
            results.append(msg)
            return "ok"

        registry.register("test.cap", handler)
        self.assertTrue(registry.has_provider("test.cap"))
        self.assertIn("test.cap", registry.list_capabilities())

        # When calling registry.invoke directly, payload is passed as-is
        invoke_results = registry.invoke("test.cap", {"key": "value"})
        self.assertEqual(invoke_results, ["ok"])
        self.assertEqual(results, [{"key": "value"}])

        registry.unregister("test.cap", handler)
        self.assertFalse(registry.has_provider("test.cap"))
        self.assertEqual(registry.invoke("test.cap", {}), [])

    def test_capability_registry_lock_free_multiple_providers(self):
        """Lock-free registry handles multiple providers correctly."""
        registry = CapabilityRegistry(thread_safe=False)

        registry.register("cap", lambda m: 1)
        registry.register("cap", lambda m: 2)
        registry.register("cap", lambda m: 3)

        results = registry.invoke("cap", {})
        self.assertEqual(results, [1, 2, 3])

    def test_component_registry_lock_free_basic(self):
        """Lock-free ComponentRegistry works for single-threaded usage."""
        registry = ComponentRegistry(thread_safe=False)
        self.assertIsNone(registry._lock)

        registry.register_class("comp", "tests.test_concurrency_stress.DummyComponent")
        component = registry.create("comp", cmp_name="test_comp")
        self.assertIsNotNone(component)
        if component:
            self.assertEqual(component.name, "test_comp")

        got = registry.get("comp")
        self.assertIs(got, component)
        self.assertIn("comp", registry.list_components())

        registry.unregister("comp")
        self.assertIsNone(registry.get("comp"))

    def test_component_registry_lock_free_clear(self):
        """Lock-free ComponentRegistry clear works correctly."""
        registry = ComponentRegistry(thread_safe=False)
        for i in range(5):
            registry.register_class(
                f"comp_{i}", "tests.test_concurrency_stress.DummyComponent"
            )
            registry.create(f"comp_{i}", cmp_name=f"comp_{i}")

        self.assertEqual(len(registry.list_components()), 5)
        registry.clear()
        self.assertEqual(len(registry.list_components()), 0)


class TestLockFreePerformance(unittest.TestCase):
    """Benchmark: lock-free vs thread-safe in single-threaded scenarios."""

    def _benchmark_capability_ops(
        self, registry: CapabilityRegistry, iterations: int
    ) -> float:
        """Return time in seconds for N register+invoke+unregister cycles."""
        start = time.perf_counter()
        for i in range(iterations):
            cap_name = f"cap_{i % 100}"

            def handler(msg):
                return i

            registry.register(cap_name, handler)
            registry.invoke(cap_name, {})
            registry.unregister(cap_name, handler)
        return time.perf_counter() - start

    def test_lock_free_is_faster_than_thread_safe(self):
        """Lock-free mode should be measurably faster in single-threaded ops."""
        iterations = 10_000

        # Warm up
        warm_registry = CapabilityRegistry(thread_safe=False)
        self._benchmark_capability_ops(warm_registry, 100)

        # Lock-free
        lf_registry = CapabilityRegistry(thread_safe=False)
        lf_time = self._benchmark_capability_ops(lf_registry, iterations)

        # Thread-safe
        ts_registry = CapabilityRegistry(thread_safe=True)
        ts_time = self._benchmark_capability_ops(ts_registry, iterations)

        # Lock-free should be faster (allow some tolerance for system noise)
        self.assertLess(
            lf_time,
            ts_time,
            f"Lock-free ({lf_time:.4f}s) should be faster than thread-safe ({ts_time:.4f}s)",
        )

        # Report speedup ratio
        ratio = ts_time / lf_time
        print(
            f"\n  Performance: lock-free={lf_time:.4f}s, thread-safe={ts_time:.4f}s, "
            f"speedup={ratio:.2f}x"
        )


if __name__ == "__main__":
    unittest.main()
