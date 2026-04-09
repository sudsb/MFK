# AGENTS.md

## Repo Overview

Communication-based component framework (v2.0): components plug into a MessageBus and communicate freely via publish/subscribe channels. The framework does NOT know what components will connect in advance.

**No external dependencies** — stdlib only. No `pyproject.toml`, `requirements.txt`, or `setup.py`.

## Commands

| Action | Command |
|--------|---------|
| Run pipeline | `python main.py` |
| Activate venv | `.venv\Scripts\activate` (Windows) |
| Run tests | `python -m unittest discover -v` or `python test_*.py` |
| Run single test | `python -m unittest test_delivery.TestDelivery.test_thread` |
| Lint code | `ruff check .` |
| Format code | `ruff format .` |
| Type check | Use mypy if installed: `mypy .` |

**Python**: 3.12, managed by `uv`. `.venv` contains only `setuptools` + `wheel`.

## Build/Lint/Test Commands

- **Test single file**: `python test_delivery.py`
- **Test all delivery modes**: `python test_delivery.py` (tests thread/process/asyncio backends)
- **Lint**: `ruff check . --fix` (auto-fix violations where possible)
- **Format**: `ruff format .` (auto-format code)
- **Type check**: No dedicated type checker configured; use IDE or install mypy separately
- **Run UI demo**: `python main.py` (Tkinter-based dual-screen demo)

## Architecture (v2.0 — Communication Model)

```
main.py                    → entrypoint: loads config, creates bus, registers components
config.json                → component definitions + bus config
framework/
  __init__.py              → public API exports
  interfaces.py            → BaseComponent ABC: handle_message(message) -> Any
  bus.py                   → MessageBus: publish/subscribe routing, channel management
  config_loader.py         → JSON → ComponentRegistry + bus config
  registry.py              → ComponentRegistry: dynamic instantiation via importlib
  pool.py                  → ObjectPool: component instance reuse
  cache.py                 → ParamCache: memoization (param hash → cached result)
  snapshot.py              → SnapshotManager: state save/restore for interruption recovery
  channels/
    base.py                → Channel ABC + Message dataclass + ChannelType enum
    normal.py              → NormalChannel: queue.Queue / multiprocessing.Queue
    highspeed.py           → HighSpeedChannel: mmap ring buffer, zero-copy
features/
  file_reader.py           → FileReader: reads file, publishes to bus
  printer.py               → ConsolePrinter: subscribes to data, prints
```

## Code Style Guidelines

### Imports
- Use `from __future__ import annotations` in all Python files for forward references
- Group imports: stdlib, then third-party, then local modules
- Use absolute imports relative to project root (no `__init__.py` in root)
- Example:
```python
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from framework.interfaces import BaseComponent
from framework.channels.base import Message
```

### Formatting
- Use `ruff format` for consistent formatting
- Line length: 88 characters (ruff default)
- Use double quotes for strings, single quotes for character literals
- Trailing commas in multi-line structures

### Naming Conventions
- **Classes**: PascalCase (e.g., `MessageBus`, `FileReader`)
- **Functions/Methods**: snake_case (e.g., `handle_message`, `on_start`)
- **Variables**: snake_case (e.g., `payload`, `channel_type`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_TIMEOUT`)
- **Private attributes**: leading underscore (e.g., `self._bus`, `self._running`)

### Type Hints
- Use comprehensive type hints throughout
- Use `Optional[T]` for nullable types instead of `T | None`
- Use `Union` sparingly; prefer specific types
- Example:
```python
def handle_message(self, message: Message) -> Any:
    ...

def __init__(self, timeout: Optional[float] = None) -> None:
    ...
```

### Docstrings
- Use Google-style docstrings for all public classes/methods
- Include parameter descriptions and return types
- Example:
```python
class FileReader(BaseComponent):
    """Reads a file and publishes its content via the message bus.

    Subscribes to 'file.read' topic, publishes to 'data.loaded' topic.

    Params (via config.json):
      - path: path to the file (default: 'sample.txt')
      - output_key: key for the published data (default: 'file_content')
    """
```

### Error Handling
- Use specific exception types, not bare `except:`
- Log errors appropriately using the `logging` module
- Return error information in message payloads rather than raising exceptions
- Example:
```python
try:
    with open(self.path, "r", encoding="utf-8") as f:
        content = f.read()
except FileNotFoundError:
    error_msg = f"File not found: {self.path}"
    self._bus.publish("data.loaded", payload={"error": error_msg}, sender=self.name)
    return {"error": error_msg}
```

### Component Patterns
- Always call `super().__init__(**params)` in component `__init__`
- Extract parameters with defaults in `__init__`
- Use `self.params` dict for runtime parameter access
- Implement `on_start()` for subscriptions, `on_stop()` for cleanup
- Publish results via `self._bus.publish()` with descriptive sender names

### Logging
- Use module-level loggers: `log = logging.getLogger(__name__)`
- Log at appropriate levels: DEBUG for internal state, INFO for important events, ERROR for failures
- Include component name in log messages for traceability

### Security Best Practices
- No secrets or credentials in code or config files
- Use UTF-8 encoding for file operations
- Validate file paths to prevent directory traversal
- Sanitize error messages to avoid information leakage

## Pipeline Config (`config.json`)

Each component:
```json
{
  "name": "reader",
  "class": "features.file_reader.FileReader",
  "params": { "path": "sample.txt", "output_key": "file_content" },
  "subscribes": ["file.read"],
  "publishes": ["data.loaded"]
}
```

Bus config:
```json
{
  "bus": { "default_channel": "highspeed" }
}
```

- `default_channel`: `highspeed` (mmap, same-process, μs latency) | `normal` (queue-based, cross-process, ms latency)

## Component Contract

Subclass `BaseComponent`, implement `handle_message(message: Message) -> Any`:
- Components subscribe to topics via `self._bus.subscribe(topic, self.handle_message)`
- Components publish via `self._bus.publish(topic, payload, sender=self.name)`
- `on_start()`: lifecycle hook for subscribing to topics
- `on_stop()`: lifecycle hook for cleanup
- `attach_bus(bus)`: called by framework, sets `self._bus` and `self._running = True`
- `detach_bus()`: called by framework, clears `self._bus` and `self._running = False`

## Channel Types

| Feature | NormalChannel | HighSpeedChannel |
|---------|--------------|-----------------|
| Backend | `queue.Queue` / `multiprocessing.Queue` | `mmap` ring buffer |
| Latency | ~ms | ~μs |
| Cross-process | ✅ | ❌ (same-process only) |
| Payload limit | None | Pre-allocated (default 1024B/slot) |
| Serialization | pickle (for cross-process) | pickle + zero-copy via `memoryview` |

## Performance Layer

- **ObjectPool** (`pool.py`): `acquire()` / `release()` for component instance reuse. Factory-based, configurable max_size.
- **ParamCache** (`cache.py`): SHA256 key from params dict, TTL expiration, LRU eviction. `get()` / `set()` / `stats()`.
- **SnapshotManager** (`snapshot.py`): Captures component state + pending messages + cache. `capture()` / `restore()` / `persist()` (to disk JSON) / `load()`.

## Conventions

- All imports relative to project root (no `__init__.py` in root). Run from `D:\code-project\python\mfk`.
- Component params accessed via `self.params` dict and extracted in `__init__` with defaults.
- File paths in `config.json` are relative to project root.

## IDE/Editor Configuration

- No Cursor rules (.cursor/rules/) or .cursorrules found
- No Copilot rules (.github/copilot-instructions.md) found
- Use VS Code with Python extension for best development experience
- Configure Ruff as formatter and linter in your IDE

## Stability Notes

- **UI thread safety**: Tkinter widget calls from bus handlers are marshaled to main thread via `root.after(0, ...)`. Do NOT call Tkinter methods directly from bus handlers.
- **Process mode**: `subscribe()` requires `handler_info` for component reconstruction in child processes. Without it, falls back to thread delivery with a warning.
- **Component validation**: `registry.create()` instantiates via importlib. Ensure class paths are correct and `__init__` params are serializable for process mode.
- **test_run_pipeline.py** and **debug_pipeline.py** are legacy files referencing removed API. Update or remove as needed.
