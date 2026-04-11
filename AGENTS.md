# AGENTS.md

## Repo Overview

Communication-based component framework (v2.0): components plug into a MessageBus and communicate via publish/subscribe. The framework does NOT know what components will connect in advance.

**Pure stdlib** — zero external dependencies. Python 3.12+, managed by `uv`. No `pyproject.toml` or `setup.py`.

## Commands

| Action | Command |
|--------|---------|
| Run UI demo | `python main.py` |
| Run config-driven pipeline | `python test_config.py` |
| Generate config.json interactively | `python generate_config.py` |
| Generate component boilerplate | `python generate_component.py` |
| Test all delivery backends | `python test_delivery.py` (thread/process/asyncio) |
| Run full test suite | `python -m unittest discover -s tests` |
| Test single class | `python -m unittest tests.test_framework.TestObjectPoolContention` |
| Test single backend | `python -m unittest test_delivery.TestDelivery.test_thread` |
| Lint | `ruff check .` / `ruff check . --fix` |
| Format | `ruff format .` |

Run all commands from project root.

## Architecture

```
main.py              → Tkinter UI entrypoint (dual-screen demo, NOT config-driven)
test_config.py       → Config-driven pipeline: loads config.json → creates bus + components
config.json          → Component definitions + bus config (used by config_loader, NOT by main.py)
generate_config.py   → Interactive CLI: generates config.json via Q&A
generate_component.py → Interactive CLI: generates BaseComponent subclass + JSON config snippet
framework/
  __init__.py        → Public API exports
  interfaces.py      → BaseComponent ABC (handle_message, on_start/on_stop, attach/detach_bus)
  bus.py             → MessageBus: pub/sub routing, 3 delivery backends, channel management
  config_loader.py   → load_framework_config(): JSON → ComponentRegistry + bus config
  registry.py        → ComponentRegistry: dynamic instantiation via importlib
  pool.py            → ObjectPool: factory-based component instance reuse
  cache.py           → ParamCache: SHA256 param-hash memoization with TTL + LRU
  snapshot.py        → SnapshotManager: state capture/restore for interruption recovery
  _test_helpers.py   → Test doubles: BadInitComponent, LifecycleComponent (DO NOT use in prod)
  channels/
    base.py          → Channel ABC, Message dataclass, ChannelType enum
    normal.py        → NormalChannel: queue.Queue / multiprocessing.Queue
    highspeed.py     → HighSpeedChannel: mmap ring buffer, zero-copy (same-process only)
features/
  file_reader.py     → FileReader: reads file, publishes to bus
  printer.py         → ConsolePrinter: subscribes to data, prints
  screen1.py         → Screen1 UI component
  screen2.py         → Screen2 UI component
  ui_app.py          → UIApp: Tkinter dual-screen application
```

## Entry Points (Two Modes)

| File | Mode | What it does |
|------|------|-------------|
| `main.py` | UI | Creates Screen1/Screen2, launches `UIApp`. Does NOT use config_loader. |
| `test_config.py` | Pipeline | Loads `config.json` via `load_framework_config()`, creates bus + components, runs file→print pipeline. |

## Delivery Modes (MessageBus)

`MessageBus` has 3 delivery backends controlled by `delivery_mode` param:

| Mode | Backend | Use Case | Gotcha |
|------|---------|----------|--------|
| `"thread"` (default) | `ThreadPoolExecutor` daemon threads | I/O-bound handlers | GIL limits CPU parallelism |
| `"process"` | `multiprocessing.Pool` child processes | CPU-bound, isolation | **Requires `handler_info` on `subscribe()`** or falls back to thread with warning |
| `"asyncio"` | Dedicated event loop thread | Async-native components | Coroutines awaited directly; sync handlers via `run_in_executor` |

### Process Mode `handler_info` (CRITICAL)

Process delivery re-instantiates the component in a child process. `subscribe()` MUST include:

```python
bus.subscribe("topic", handler, handler_info={
    "module": "features.file_reader",   # module path
    "class_name": "FileReader",          # class name
    "method_name": "handle_message",     # method to call
    "params": {"path": "data.txt"}       # __init__ kwargs
})
```

Without `handler_info`, process mode falls back to thread delivery with a warning. See `docs/process_delivery.md` and `examples/process_subscribe_example.py`.

### Cross-Process Rule

- `HighSpeedChannel` (mmap) is **NOT cross-process safe**. Use `NormalChannel` for cross-process.
- Message payloads must be picklable for process mode.
- `test_exec.py` contains `_DummyComponent` used by `test_delivery.py` for process-mode testing. Keep it import-clean (minimal deps).

## Component Contract

Subclass `BaseComponent`, implement `handle_message(message: Message) -> Any`:
- `on_start()`: subscribe to topics via `self._bus.subscribe(topic, self.handle_message)`
- `on_stop()`: cleanup resources
- Publish via `self._bus.publish(topic, payload, sender=self.name)`
- `attach_bus(bus)`: called by framework, sets `self._bus` and `self._running = True`
- `detach_bus()`: called by framework, clears `self._bus` and `self._running = False`
- Extract params in `__init__` with defaults, always call `super().__init__(**params)`

## Channel Types

| Feature | NormalChannel | HighSpeedChannel |
|---------|--------------|-----------------|
| Backend | `queue.Queue` / `multiprocessing.Queue` | `mmap` ring buffer |
| Latency | ~ms | ~μs |
| Cross-process | ✅ | ❌ (same-process only) |
| Payload limit | None | Pre-allocated (default 1020B usable/slot) |
| Blocking recv | ✅ | ❌ (non-blocking) |

## Test Structure

- **Root-level** (`test_delivery.py`, `test_config.py`, `test_exec.py`, `test_edge_cases.py`, `test_error_handling.py`, `test_ui_components.py`): Standalone scripts, run with `python <file>`.
- **`tests/`** (`test_framework.py`, `test_pickling.py`, `test_edge_cases.py`, `test_generators.py`): unittest modules, run with `python -m unittest discover -s tests`.

## Stability Notes

- **UI thread safety**: Tkinter calls from bus handlers MUST be marshaled via `root.after(0, ...)`. Never call Tkinter methods directly from bus handlers. See `features/ui_app.py` for the pattern.
- **Import paths**: All imports relative to project root (no `__init__.py` in root). `framework/__init__.py` exports the public API.
- `config.json` file paths are relative to project root.

## Detailed Docs

- `USAGE.md` — Comprehensive API reference with full examples (Chinese)
- `UPGRADE.md` — Breaking changes guide, pickling requirements, migration checklist
- `docs/process_delivery.md` — Process mode delivery details
- `README.md` — Overview and quick start (Chinese)
