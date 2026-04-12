"""Config-driven pipeline: loads config.json, creates bus + components, runs pipeline."""

import time
from framework.bus import MessageBus
from framework.config_loader import load_framework_config

bus_cfg = load_framework_config("config.json")
registry = bus_cfg["registry"]
bus = MessageBus(default_channel=bus_cfg["bus_config"]["default_channel"])

components = []
for comp_cfg in bus_cfg["components_cfg"]:
    comp = registry.create(comp_cfg["name"], **comp_cfg.get("params", {}))
    if comp:
        bus.register_component(comp)
        components.append(comp)

# Invoke the file.read capability -- we don't care who provides it
results = bus.invoke("file.read", payload={})
print(f"Invocation results: {results}")

# Wait for async handlers and event propagation
time.sleep(1)
bus.shutdown()
