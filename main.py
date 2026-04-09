"""UI Application entrypoint - launches dual-screen UI integrated with framework MessageBus."""

import logging
from framework.bus import MessageBus
from framework.channels.base import ChannelType
from features.screen1 import Screen1
from features.screen2 import Screen2
from features.ui_app import UIApp


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # Create message bus
    bus = MessageBus(default_channel=ChannelType.HIGH_SPEED)

    # Register UI screen components
    screen1 = Screen1()
    screen2 = Screen2()
    bus.register_component(screen1)
    bus.register_component(screen2)

    # Launch UI application (bus is shared for cross-screen communication)
    app = UIApp(bus=bus)
    app.run()

    # Cleanup
    bus.shutdown()


if __name__ == "__main__":
    main()
