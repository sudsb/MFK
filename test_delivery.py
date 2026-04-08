"""Test all three delivery backends: thread, process, asyncio."""

from __future__ import annotations

import asyncio
import logging
import time
from framework.bus import MessageBus
from framework.channels.base import ChannelType, Message

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("test_delivery")


def make_handler(label: str):
    """Return a handler that logs when called."""

    def handler(message: Message) -> None:
        log.info(
            "[%s] received topic=%s payload=%s", label, message.topic, message.payload
        )

    return handler


def make_async_handler(label: str):
    """Return an async handler."""

    async def handler(message: Message) -> None:
        log.info(
            "[async %s] received topic=%s payload=%s",
            label,
            message.topic,
            message.payload,
        )
        await asyncio.sleep(0.01)

    return handler


# ---------------------------------------------------------------------------
# 1. Thread backend
# ---------------------------------------------------------------------------
def test_thread() -> None:
    log.info("=== Testing THREAD backend ===")
    bus = MessageBus(
        default_channel=ChannelType.HIGH_SPEED,
        delivery_mode="thread",
        max_workers=4,
    )
    bus.subscribe("test.topic", make_handler("subscriber-A"))
    bus.subscribe("test.topic", make_handler("subscriber-B"))

    result = bus.publish("test.topic", payload={"data": 42}, sender="test_thread")
    log.info("Publish returned: %s", result)

    time.sleep(0.3)  # let daemon threads finish
    bus.shutdown()
    log.info("Thread backend OK\n")


# ---------------------------------------------------------------------------
# 2. Process backend
# ---------------------------------------------------------------------------
def test_process() -> None:
    log.info("=== Testing PROCESS backend ===")
    bus = MessageBus(
        default_channel=ChannelType.NORMAL,
        delivery_mode="process",
        max_workers=2,
    )
    # Process mode requires handler_info for component reconstruction
    bus.subscribe(
        "test.topic",
        make_handler("process-subscriber"),
        handler_info={
            "module": "test_exec",
            "class_name": "_DummyComponent",
            "method_name": "handle_message",
            "params": {},
        },
    )

    result = bus.publish(
        "test.topic", payload={"pid_test": True}, sender="test_process"
    )
    log.info("Publish returned: %s", result)

    time.sleep(1.0)  # child process needs more time
    bus.shutdown()
    log.info("Process backend OK\n")


# ---------------------------------------------------------------------------
# 3. Asyncio backend
# ---------------------------------------------------------------------------
def test_asyncio() -> None:
    log.info("=== Testing ASYNCIO backend ===")
    bus = MessageBus(
        default_channel=ChannelType.HIGH_SPEED,
        delivery_mode="asyncio",
    )
    bus.subscribe("test.topic", make_async_handler("async-A"))
    bus.subscribe("test.topic", make_handler("sync-fallback"))

    result = bus.publish("test.topic", payload={"async": True}, sender="test_asyncio")
    log.info("Publish returned: %s", result)

    time.sleep(0.5)  # let event loop process messages
    bus.shutdown()
    log.info("Asyncio backend OK\n")


if __name__ == "__main__":
    test_thread()
    test_process()
    test_asyncio()
    print("\nAll three delivery backends passed.")
