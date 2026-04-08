# AGENTS.md

## Repo Overview

Communication-based component framework (v2.0): components plug into a MessageBus and communicate freely via publish/subscribe channels. The framework does NOT know what components will connect in advance.

**No external dependencies** — stdlib only. No `pyproject.toml`, `requirements.txt`, or `setup.py`.

## Commands

| Action | Command |
|--------|---------|
| Run pipeline | `python main.py` |
| Activate venv | `.venv\Scripts\activate` (Windows) |

**Python**: 3.11, managed by `uv`. `.venv` contains only `setuptools` + `wheel`.

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

- All imports relative to project root (no `__init__.py` in root). Run from `D:\code-project\python\content`.
- Component params accessed via `self.params` dict and extracted in `__init__` with defaults.
- File paths in `config.json` are relative to project root.

## Stability Notes

- **UI thread safety**: Tkinter widget calls from bus handlers are marshaled to main thread via `root.after(0, ...)`. Do NOT call Tkinter methods directly from bus handlers.
- **Process mode**: `subscribe()` requires `handler_info` for component reconstruction in child processes. Without it, falls back to thread delivery with a warning.
- **Component validation**: `registry.create()` instantiates via importlib. Ensure class paths are correct and `__init__` params are serializable for process mode.
- **test_run_pipeline.py** and **debug_pipeline.py** are legacy files referencing removed API. Update or remove as needed.
