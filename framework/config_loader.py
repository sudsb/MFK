import json
import logging
from typing import Any, Dict
from .registry import ComponentRegistry
from .channels.base import ChannelType

log = logging.getLogger(__name__)


def load_framework_config(config_path: str) -> Dict[str, Any]:
    """Load framework configuration from JSON.

    Expected config structure:
    {
      "components": [
        {
          "name": "reader",
          "class": "features.file_reader.FileReader",
          "params": {"path": "sample.txt", "output_key": "file_content"},
          "subscribes": ["file.read"],
          "publishes": ["data.loaded"]
        }
      ],
      "bus": {
        "default_channel": "highspeed"
      }
    }

    Returns dict with 'registry', 'components', 'bus_config'.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If config file contains invalid JSON.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg: Dict[str, Any] = json.load(f)
    except FileNotFoundError:
        log.error("Config file not found: %s", config_path)
        raise
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in config file %s: %s", config_path, e)
        raise ValueError(f"Invalid JSON in config file {config_path}: {e}") from e
    except OSError as e:
        log.error("Failed to read config file %s: %s", config_path, e)
        raise

    registry = ComponentRegistry()

    for comp_cfg in cfg.get("components", []):
        name = comp_cfg.get("name")
        class_path = comp_cfg.get("class")

        if not name or not class_path:
            log.warning("Skipping component: missing 'name' or 'class'")
            continue

        registry.register_class(name, class_path)

    bus_config = cfg.get("bus", {})
    default_channel_str = bus_config.get("default_channel", "highspeed")
    default_channel = (
        ChannelType.HIGH_SPEED
        if default_channel_str == "highspeed"
        else ChannelType.NORMAL
    )

    return {
        "registry": registry,
        "components_cfg": cfg.get("components", []),
        "bus_config": {"default_channel": default_channel},
    }
