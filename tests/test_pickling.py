"""Pickling validation tests for Message and channel messages.

These tests ensure dataclasses and messages used by the framework are
picklable for process-mode delivery and for cross-process channels.

Pure stdlib only; uses unittest.
"""

from __future__ import annotations

import pickle
import unittest

from framework.channels.base import Message, ChannelType


class Payload:
    def __init__(self, v):
        self.v = v

    def __eq__(self, other):
        return isinstance(other, Payload) and self.v == other.v


class TestPickling(unittest.TestCase):
    def test_message_picklable_simple_payload(self):
        msg = Message(topic="test.simple", payload={"x": 1}, sender="tester")
        data = pickle.dumps(msg)
        loaded = pickle.loads(data)
        self.assertEqual(loaded.topic, msg.topic)
        self.assertEqual(loaded.payload, msg.payload)
        self.assertEqual(loaded.sender, msg.sender)
        self.assertEqual(loaded.channel_type, msg.channel_type)

    def test_message_picklable_with_custom_object(self):
        p = Payload(99)
        msg = Message(topic="test.obj", payload=p, sender="tester")
        data = pickle.dumps(msg)
        loaded = pickle.loads(data)
        # payload equality is implemented above
        self.assertEqual(loaded.payload, msg.payload)

    def test_channel_type_enum_picklable(self):
        # Ensure ChannelType enum members survive pickling
        ct = ChannelType.HIGH_SPEED
        data = pickle.dumps(ct)
        loaded = pickle.loads(data)
        self.assertIs(loaded, ChannelType.HIGH_SPEED)


if __name__ == "__main__":
    unittest.main()
