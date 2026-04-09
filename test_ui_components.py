import time
import logging
from framework.bus import MessageBus
from framework.channels.base import ChannelType
from features.screen1 import Screen1
from features.screen2 import Screen2

logging.basicConfig(level=logging.INFO)

bus = MessageBus(default_channel=ChannelType.HIGH_SPEED, delivery_mode="thread")
screen1 = Screen1()
screen2 = Screen2()

bus.register_component(screen1)
bus.register_component(screen2)

print("Registered. Publishing message.")
bus.publish(
    "ui.navigate_to_screen1", payload={"message": "hello from test", "source": "test"}
)

time.sleep(1)
bus.shutdown()
print("Shutdown complete.")
