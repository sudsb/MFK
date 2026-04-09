"""Example demonstrating process-mode subscription with handler_info.

Run this script from the repository root. It creates a MessageBus with
delivery_mode='process', registers a simple component class, subscribes to a
topic using handler_info (so the child process can re-instantiate the
component), and publishes a message. The handler runs inside a child
process and prints incoming message details.
"""

import time
import logging

from framework.bus import MessageBus
from framework.channels.base import ChannelType


logging.basicConfig(level=logging.DEBUG)


class SimpleWorker:
    """A minimal component class with a handle_message method.

    Note: The class must be importable by module path when re-instantiated in
    the child process. This file is under "examples" so we construct handler_info
    to point to the module path 'examples.process_subscribe_example.SimpleWorker'.
    When running as a script, Python will set module name to '__main__', so for
    process re-import to work, ensure this package is importable (run via
    `python -m examples.process_subscribe_example` or adjust PYTHONPATH).
    For simplicity in this example we'll demonstrate using a local class via
    module import by referencing the full module path below.

    The safer pattern in real code is to place component classes inside a
    package module (e.g. features.my_worker) so child processes can import it
    by name.
    """

    def __init__(self, prefix: str = "worker"):
        self.prefix = prefix

    def handle_message(self, message):
        print(
            f"[{self.prefix}] Received in child process: topic={message.topic}, payload={message.payload}"
        )


def main() -> None:
    # Create bus in process delivery mode
    bus = MessageBus(default_channel=ChannelType.NORMAL, delivery_mode="process")

    # Handler info that _process_dispatch will use to reconstruct SimpleWorker
    # Note: The module path must be importable by child processes. If running
    # this script directly (python examples/process_subscribe_example.py), the
    # module name is __main__ and importlib cannot re-import it. To keep this
    # example simple, we refer to this file as 'examples.process_subscribe_example'
    # and rely on running via `python -m examples.process_subscribe_example` or
    # ensuring the project root is on PYTHONPATH.
    handler_info = {
        "module": "examples.process_subscribe_example",
        "class_name": "SimpleWorker",
        "method_name": "handle_message",
        "params": {"prefix": "proc"},
    }

    # Subscribe: passing a local handler (callable) plus handler_info. The
    # callable is optional for process delivery but provided here for clarity.
    bus.subscribe(
        "test.topic",
        handler=lambda msg: print("local handler got:", msg.payload),
        handler_info=handler_info,
    )

    # Publish a picklable payload
    payload = {"value": 123, "text": "hello from parent"}
    published = bus.publish("test.topic", payload)
    print("Published ->", published)

    # Wait briefly to allow process pool to run handlers
    time.sleep(1)

    bus.shutdown()


if __name__ == "__main__":
    main()
