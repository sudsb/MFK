# 框架使用说明

## 目录

- [1. 架构概述](#1-架构概述)
- [2. 快速开始](#2-快速开始)
- [3. 核心 API 详解](#3-核心-api-详解)
  - [3.1 BaseComponent](#31-basecomponent)
  - [3.2 MessageBus](#32-messagebus)
  - [3.3 Channel 系统](#33-channel-系统)
  - [3.4 ComponentRegistry](#34-componentregistry)
  - [3.5 ObjectPool](#35-objectpool)
  - [3.6 ParamCache](#36-paramcache)
  - [3.7 SnapshotManager](#37-snapshotmanager)
  - [3.8 config_loader](#38-config_loader)
- [4. 完整示例](#4-完整示例)
  - [示例1：基础发布/订阅](#示例1基础发布订阅)
  - [示例2：对象池 + 缓存](#示例2对象池--缓存)
  - [示例3：快照恢复](#示例3状态快照与恢复)
  - [示例4：双通道混合使用](#示例4双通道混合使用)
  - [示例5：自定义文件处理组件](#示例5自定义组件--文件处理器)
  - [示例6：三种投递后端对比](#示例6三种投递后端对比)
- [5. 框架优势与局限性](#5-框架优势与局限性)

---

## 1. 架构概述

### 通信模型

本框架采用 **发布/订阅（Publish/Subscribe）通信模型**。组件之间不直接调用，而是通过 `MessageBus` 进行解耦通信。框架在设计时 **不知道也不关心** 会有哪些组件接入。

- 组件通过 `publish(topic, payload)` 向指定主题发送消息
- 组件通过 `subscribe(topic, handler)` 订阅感兴趣的主题
- 消息通过 `Channel` 传输，支持两种通道：普通通道（NormalChannel）和高速通道（HighSpeedChannel）
- 每个处理器在独立的守护线程中执行，不会阻塞发布者

### 核心组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                    (应用入口)                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │  Component 1 │────▶│              │◀────│  Component 2 │ │
│  │  (Publisher) │     │  MessageBus  │     │ (Subscriber) │ │
│  └──────────────┘     │              │     └──────────────┘ │
│                       │   ┌──────┐   │                      │
│  ┌──────────────┐     │   │Channel│   │     ┌──────────────┐ │
│  │  Component 3 │────▶│   └──────┘   │◀────│  Component 4 │ │
│  │ (Subscriber) │     │              │     │  (Publisher) │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
│                                                             │
│  辅助子系统：                                                  │
│  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐  │
│  │ObjectPool  │ │ParamCache│ │  Snapshot  │ │  Registry  │  │
│  └────────────┘ └──────────┘ └────────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 数据流向

```
Component A                     MessageBus                      Component B
    │                              │                                │
    │── publish("topic", data) ──▶│                                │
    │                              │── 创建 Message 对象 ──▶        │
    │                              │── 写入 Channel ──▶             │
    │                              │── 启动线程投递 ──▶             │
    │                              │                                │── handle_message(msg)
    │                              │                                │── 处理并返回结果
    │◀─────────────────────────────│◀───────────────────────────────│
```

---

## 2. 快速开始

### 交互式配置生成（推荐）

框架提供两个 CLI 工具，可通过交互式问答自动生成配置文件和组件骨架代码，无需手动编写。

**生成 `config.json`**：
```bash
python generate_config.py
```
交互式问答流程：
1. 选择总线默认通道（normal / highspeed）
2. 逐个添加组件：名称 → 类路径 → 参数（key=value）→ 订阅主题 → 发布主题
3. 预览 JSON 并确认写入

可选参数：
- `--output PATH` / `-o PATH`：指定输出文件路径（默认 `config.json`）
- `--dry-run`：仅打印 JSON 到终端，不写文件

**生成组件骨架代码 + JSON 配置**：
```bash
python generate_component.py
```
交互式问答流程：
1. 输入组件名（snake_case，自动生成 PascalCase 类名）
2. 输入描述 → 订阅/发布主题 → 初始化参数
3. 预览 Python 代码和 JSON 配置并确认写入

可选参数：
- `--output-dir PATH` / `-d PATH`：指定输出目录（默认 `features/`）
- `--dry-run`：仅打印到终端，不写文件

### 交互示例详解

#### 示例 A：使用 `generate_config.py` 生成文件读写管道

运行 `python generate_config.py` 后，终端会依次提示：

```
============================================================
  MessageBus Framework - Configuration Generator
============================================================

Bus default_channel (normal, highspeed (default: highspeed)):
```
直接回车选择默认 `highspeed`。

```
Add components? [Y/n]:
```
输入 `y` 开始添加第一个组件：

```
--- New Component ---
Component name (e.g., reader): reader
Full class path (e.g., features.file_reader.FileReader): features.file_reader.FileReader
  Enter parameters as key=value (one per line, empty line to finish):
  param: path=sample.txt
  param: output_key=file_content
  param:
Subscribe topics (comma-separated, e.g., file.read): file.read
Publish topics (comma-separated, e.g., data.loaded): data.loaded

  Component 'reader' added.
Add another component? [y/N]:
```
输入 `y` 添加第二个组件：

```
--- New Component ---
Component name (e.g., reader): printer
Full class path (e.g., features.file_reader.FileReader): features.printer.ConsolePrinter
  Enter parameters as key=value (one per line, empty line to finish):
  param: input_key=file_content
  param:
Subscribe topics (comma-separated, e.g., file.read): data.loaded
Publish topics (comma-separated, e.g., data.loaded):

  Component 'printer' added.
Add another component? [y/N]: n
```
输入 `n` 结束添加，预览生成的 JSON：

```
============================================================
  Generated Configuration:
============================================================
{
  "components": [
    {
      "name": "reader",
      "class": "features.file_reader.FileReader",
      "params": {
        "path": "sample.txt",
        "output_key": "file_content"
      },
      "subscribes": ["file.read"],
      "publishes": ["data.loaded"]
    },
    {
      "name": "printer",
      "class": "features.printer.ConsolePrinter",
      "params": {
        "input_key": "file_content"
      },
      "subscribes": ["data.loaded"],
      "publishes": []
    }
  ],
  "bus": {
    "default_channel": "highspeed"
  }
}
============================================================
Write to file? [Y/n]:
```
确认无误后回车，文件写入 `config.json`。

**提示**：首次使用建议 `--dry-run` 预览输出，确认格式后再实际写入。

#### 示例 B：使用 `generate_component.py` 生成数据处理组件

运行 `python generate_component.py` 后：

```
============================================================
  Component Generator for MessageBus Framework
============================================================

Component name (e.g. data_processor): data_filter
Short description (e.g. Processes incoming data): Filters and transforms data streams
Subscribe topics (comma-separated, empty for none): data.raw
Publish topics (comma-separated, empty for none): data.filtered
Init parameters (key=default pairs, one per line. 'None' = required, empty line to finish):
  param> mode=None
  param> threshold=0.5
  param>
Output directory (default: features):
```
参数说明：
- `mode=None` — 必需参数，无默认值
- `threshold=0.5` — 可选参数，默认 0.5

确认后预览生成的 Python 代码：

```python
"""Filters and transforms data streams."""

from __future__ import annotations

from typing import Any

from framework.channels.base import Message
from framework.interfaces import BaseComponent


class DataFilter(BaseComponent):
    """Filters and transforms data streams."""

    name: str = "data_filter"

    def __init__(self, mode: Any, threshold: Any = 0.5, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.threshold = threshold

    def on_start(self) -> None:
        """Subscribe to topics."""
        self._bus.subscribe("data.raw", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        """Process incoming messages."""
        payload = message.payload
        # TODO: Implement message handling logic
        # Publish to: "data.filtered"
        pass

    def on_stop(self) -> None:
        """Cleanup resources."""
        pass
```

以及对应的 JSON 配置片段：

```json
{
  "name": "data_filter",
  "class": "features.DataFilter",
  "params": {
    "mode": null,
    "threshold": 0.5
  },
  "subscribes": [
    "data.raw"
  ],
  "publishes": [
    "data.filtered"
  ]
}
```

确认后将文件写入 `features/data_filter.py` 和 `features/data_filter_config.json`。

**下一步**：将 JSON 片段中的内容合并到 `config.json` 的 `components` 数组中，然后运行 `python test_config.py` 即可接入管道。

### 手动编写配置文件

如果你更倾向于手动编辑 `config.json`，请参考下方格式说明。

### 最小运行示例

**步骤 1**：创建 `config.json`

```json
{
  "components": [
    {
      "name": "reader",
      "class": "features.file_reader.FileReader",
      "params": { "path": "sample.txt", "output_key": "file_content" },
      "subscribes": ["file.read"],
      "publishes": ["data.loaded"]
    },
    {
      "name": "printer",
      "class": "features.printer.ConsolePrinter",
      "params": { "input_key": "file_content" },
      "subscribes": ["data.loaded"]
    }
  ],
  "bus": {
    "default_channel": "highspeed"
  }
}
```

**步骤 2**：创建入口脚本

```python
import logging
from framework.config_loader import load_framework_config
from framework.bus import MessageBus
from framework.channels.base import ChannelType

def main():
    logging.basicConfig(level=logging.INFO)

    # 加载配置
    config = load_framework_config("config.json")
    registry = config["registry"]
    bus_config = config["bus_config"]

    # 创建总线
    bus = MessageBus(default_channel=bus_config["default_channel"])

    # 实例化并注册组件
    components = []
    for comp_cfg in config["components_cfg"]:
        comp = registry.create(comp_cfg["name"], **comp_cfg.get("params", {}))
        if comp:
            bus.register_component(comp)
            components.append(comp)

    # 触发第一个组件
    bus.publish("file.read", payload={"trigger": True}, sender="main")

    # 等待消息处理
    import time
    time.sleep(0.5)

    # 清理
    bus.shutdown()

if __name__ == "__main__":
    main()
```

**步骤 3**：运行

```bash
python main.py
```

### config.json 完整字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `components` | `array` | 是 | 组件定义列表 |
| `components[].name` | `string` | 是 | 组件唯一标识名 |
| `components[].class` | `string` | 是 | 类路径，格式 `"模块.类名"` |
| `components[].params` | `object` | 否 | 传递给组件构造函数的参数 |
| `components[].subscribes` | `array[string]` | 否 | 订阅的主题列表（仅文档用途，组件需在 `on_start` 中自行订阅） |
| `components[].publishes` | `array[string]` | 否 | 发布的主题列表（仅文档用途） |
| `bus` | `object` | 否 | 总线配置 |
| `bus.default_channel` | `string` | 否 | 默认通道类型：`"highspeed"` 或 `"normal"`，默认 `"highspeed"` |

---

## 3. 核心 API 详解

### 3.1 BaseComponent

**文件**：`framework/interfaces.py`

所有组件的抽象基类。组件必须继承此类并实现 `handle_message` 方法。

#### 类属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | `"unnamed"` | 组件名称，子类应重写 |

#### 构造方法

```python
def __init__(self, **params: Any) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `**params` | `Any` | — | 任意关键字参数，存储在 `self.params` 中 |

构造后实例属性：
- `self.params: Dict[str, Any]` — 构造参数副本
- `self._bus: Optional[MessageBus]` — 消息总线引用，初始为 `None`
- `self._running: bool` — 运行状态标志，初始为 `False`

#### 方法

##### `attach_bus(bus: MessageBus) -> None`

由框架调用，为组件注入消息总线访问权限。

| 参数 | 类型 | 说明 |
|------|------|------|
| `bus` | `MessageBus` | 要附加的消息总线实例 |

行为：设置 `self._bus = bus`，`self._running = True`。

##### `detach_bus() -> None`

由框架调用，断开组件与总线的连接。

行为：设置 `self._running = False`，`self._bus = None`。

##### `handle_message(message: Message) -> Any` *(抽象方法)*

处理传入消息。子类 **必须** 实现此方法。

| 参数 | 类型 | 说明 |
|------|------|------|
| `message` | `Message` | 包含 topic、payload、sender 等信息的消息对象 |

**返回值**：任意类型，可返回给其他订阅者使用。

**线程安全**：每个消息在独立的守护线程中调用此方法。实现中涉及共享状态时需自行加锁。

##### `on_start() -> None`

生命周期钩子。组件激活时调用，子类可重写此方法以订阅主题。

默认实现为空操作。

##### `on_stop() -> None`

生命周期钩子。组件停用时调用，子类可重写此方法以清理资源。

默认实现为空操作。

##### `is_running` *(属性)*

只读属性，返回 `self._running` 的值。

#### 自定义组件实现规范

1. 继承 `BaseComponent`，设置 `name` 类属性
2. 在 `__init__` 中调用 `super().__init__(**params)`，然后提取自有参数
3. 在 `on_start` 中通过 `self._bus.subscribe()` 订阅主题
4. 实现 `handle_message` 处理逻辑
5. 需要发布消息时通过 `self._bus.publish()` 发送
6. 在 `on_stop` 中清理资源

---

### 3.2 MessageBus

**文件**：`framework/bus.py`

中央消息路由器，负责组件间的消息路由和通道管理。

#### 构造方法

```python
def __init__(
    self,
    default_channel: ChannelType = ChannelType.HIGH_SPEED,
    delivery_mode: str = "thread",
    max_workers: int = 0,
) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_channel` | `ChannelType` | `ChannelType.HIGH_SPEED` | 未指定通道类型时使用的默认通道 |
| `delivery_mode` | `str` | `"thread"` | 消息投递后端：`"thread"` / `"process"` / `"asyncio"` |
| `max_workers` | `int` | `0`（自动 = CPU 核数） | 线程池/进程池的最大工作进程数 |

**投递后端详解**：

| 模式 | 实现 | 适用场景 | 注意事项 |
|------|------|----------|----------|
| `"thread"` | `ThreadPoolExecutor` + 守护线程 | I/O 密集型任务，最常用 | 受 GIL 限制，CPU 密集任务不会真正并行 |
| `"process"` | `multiprocessing.Pool` 子进程 | CPU 密集型任务，需要进程隔离 | 组件必须可通过 `module + class_name + params` 在子进程中重新实例化；订阅时需传 `handler_info` |
| `"asyncio"` | 独立事件循环线程 + `run_coroutine_threadsafe` | 异步原生组件，大量并发 I/O | 异步 handler（`async def`）直接 await；同步 handler 通过 `run_in_executor` 执行 |

内部状态：
- `self._subscribers: Dict[str, List[Dict]]` — 主题到处理器条目列表
- `self._channels: Dict[str, Any]` — 主题到通道实例的映射
- `self._thread_pool: Optional[ThreadPoolExecutor]` — 线程池（thread 模式）
- `self._process_pool: Optional[multiprocessing.Pool]` — 进程池（process 模式）
- `self._event_loop: Optional[asyncio.AbstractEventLoop]` — 事件循环（asyncio 模式）
- `self._lock: threading.Lock` — 保护内部状态的线程锁
- `self._components: Dict[str, Any]` — 已注册组件的字典

#### 方法

##### `subscribe(topic, handler, channel_type=None, handler_info=None) -> None`

订阅一个主题。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic` | `str` | — | 主题名称 |
| `handler` | `Callable[[Message], Any]` | — | 消息处理函数，可为普通函数、绑定方法或协程函数（`async def`） |
| `channel_type` | `Optional[ChannelType]` | `None` | 指定通道类型，为 `None` 时使用 `default_channel` |
| `handler_info` | `Optional[Dict[str, Any]]` | `None` | **仅 process 模式需要**：组件重建信息，格式见下方 |

**`handler_info` 格式（process 模式必传）**：
```python
{
    "module": "features.file_reader",     # 模块路径
    "class_name": "FileReader",            # 类名
    "method_name": "handle_message",       # 处理方法名
    "params": {"path": "data.txt"}         # 构造参数
}
```

行为：
- 将处理器追加到主题的处理器列表
- 若主题尚无通道，自动创建对应类型的通道
- 线程安全（使用 `_lock`）

##### `unsubscribe(topic, handler) -> None`

从主题取消订阅一个处理器。

| 参数 | 类型 | 说明 |
|------|------|------|
| `topic` | `str` | 主题名称 |
| `handler` | `Callable[[Message], Any]` | 要移除的处理器函数 |

行为：从处理器列表中移除，若不存在则静默忽略。线程安全。

##### `publish(topic, payload, sender="", channel_type=None, ttl=0) -> bool`

向主题发布消息。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic` | `str` | — | 目标主题 |
| `payload` | `Any` | — | 消息负载数据 |
| `sender` | `str` | `""` | 发送者标识 |
| `channel_type` | `Optional[ChannelType]` | `None` | 指定通道类型 |
| `ttl` | `int` | `0` | 生存跳数，0 表示无限制 |

**返回值**：`True` 表示有处理器接收并投递，`False` 表示无订阅者。

行为：
1. 若无通道则自动创建
2. 构造 `Message` 对象并写入通道
3. 为每个处理器启动一个守护线程进行投递
4. 异常在投递时被捕获并记录日志，不影响其他处理器

##### `register_component(component) -> None`

注册组件到总线。

| 参数 | 类型 | 说明 |
|------|------|------|
| `component` | `Any` | 组件实例，需有 `name` 属性 |

行为：
- 使用 `component.name` 作为键存储（若无 `name` 则用 `id(component)`）
- 自动调用 `component.attach_bus(self)`

##### `unregister_component(name) -> None`

注销组件。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 组件名称 |

行为：从组件字典移除，并调用 `component.detach_bus()`。

##### `get_channel(topic, channel_type) -> Any`

获取或创建指定主题的通道。

| 参数 | 类型 | 说明 |
|------|------|------|
| `topic` | `str` | 主题名称 |
| `channel_type` | `ChannelType` | 通道类型 |

**返回值**：对应的 `Channel` 实例。

##### `shutdown() -> None`

关闭总线、投递后端及所有通道。

**关闭顺序**（确保组件能在总线可用时清理订阅）：
1. **先分离组件**：对所有已注册组件调用 `detach_bus()`（触发 `on_stop` 并清空总线引用）
2. **关闭投递后端**：等待正在执行的处理器完成
3. **清理通道和订阅**：关闭所有通道，清空订阅者字典

各后端清理行为：
- `"thread"` 模式：关闭 `ThreadPoolExecutor`，等待所有任务完成
- `"process"` 模式：先尝试 `close()` + `join()` 优雅关闭，失败则 `terminate()` 强制终止
- `"asyncio"` 模式：取消所有 pending 任务，等待 100ms 后停止事件循环，关闭 loop 线程

所有异常被捕获并记录日志，不会抛出。

---

### 3.3 Channel 系统

**文件**：
- `framework/channels/base.py` — 基类、Message、ChannelType
- `framework/channels/normal.py` — NormalChannel
- `framework/channels/highspeed.py` — HighSpeedChannel

#### ChannelType 枚举

```python
class ChannelType(Enum):
    NORMAL = "normal"       # 普通通道，基于队列
    HIGH_SPEED = "highspeed" # 高速通道，基于 mmap 环形缓冲区
```

#### Message 数据类

```python
@dataclass
class Message:
    topic: str                          # 主题/路由键
    payload: Any                        # 负载数据（跨进程需可 pickle）
    sender: str = ""                    # 发送者标识
    timestamp: float = time.monotonic() # 单调时间戳
    channel_type: ChannelType = ChannelType.NORMAL  # 通道类型
    ttl: int = 0                        # 生存跳数，0=无限制
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic` | `str` | — | 消息主题，用于路由 |
| `payload` | `Any` | — | 任意数据，跨进程场景需可被 `pickle` 序列化 |
| `sender` | `str` | `""` | 发送者标识符 |
| `timestamp` | `float` | `time.monotonic()` | 创建时的单调时间戳 |
| `channel_type` | `ChannelType` | `ChannelType.NORMAL` | 消息经过的通道类型 |
| `ttl` | `int` | `0` | 跳数限制，0 表示不限制 |

#### Channel 抽象基类

所有通道必须实现的接口：

| 方法 | 签名 | 说明 |
|------|------|------|
| `send` | `(message: Message) -> bool` | 发送消息，成功返回 `True` |
| `recv` | `(timeout: Optional[float] = None) -> Optional[Message]` | 接收消息，`timeout=None` 阻塞，`timeout=0` 非阻塞 |
| `close` | `() -> None` | 关闭通道并释放资源 |
| `channel_type` *(属性)* | `-> ChannelType` | 返回通道类型 |
| `size` *(属性)* | `-> int` | 返回等待接收的消息数量 |

#### NormalChannel

**文件**：`framework/channels/normal.py`

基于 `queue.Queue` 或 `multiprocessing.Queue` 的线程安全通道。

##### 构造方法

```python
def __init__(self, name: str, maxsize: int = 0, cross_process: bool = False) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | — | 通道名称（人类可读） |
| `maxsize` | `int` | `0` | 队列最大长度，`0` 表示无限制 |
| `cross_process` | `bool` | `False` | 为 `True` 时使用 `multiprocessing.Queue` 支持跨进程通信 |

##### 行为说明

- `cross_process=False`：使用 `queue.Queue`，同一进程内线程间通信
- `cross_process=True`：使用 `multiprocessing.Queue`，通过管道序列化消息实现跨进程
- `send()`：非阻塞放入队列，队列满时返回 `False`
- `recv()`：支持阻塞/非阻塞/超时三种模式，**始终返回 `None` 而非抛出异常**：
  - 超时或队列为空 → 返回 `None`
  - 检测到关闭哨兵 → 返回 `None`
  - 跨进程管道关闭（`EOFError`/`OSError`）→ 记录日志后返回 `None`
  - 其他意外错误 → 记录日志后返回 `None`
- `close()`：插入可 pickle 的哨兵对象通知等待的接收方，先尝试非阻塞 put，失败则回退到短时阻塞 put；所有失败静默处理，通道逻辑上已关闭

#### HighSpeedChannel

**文件**：`framework/channels/highspeed.py`

基于匿名 `mmap` 环形缓冲区的低延迟通道，适用于同进程高速通信。

##### 构造方法

```python
def __init__(self, name: str, slot_count: int = 64, slot_size: int = 1024) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | — | 通道名称 |
| `slot_count` | `int` | `64` | 环形缓冲区槽位数 |
| `slot_size` | `int` | `1024` | 每个槽位的字节数（含 4 字节长度前缀） |

##### 行为说明

- 每个槽位实际可用数据空间 = `slot_size - 4` 字节（4 字节用于存储 pickle 数据长度）
- 默认配置下每槽可用 1020 字节，总缓冲区大小 = `8 + 64 * 1024 = 65544` 字节
- `send()` 时若缓冲区满则返回 `False`（不阻塞）
- `recv()` 为非阻塞模式，缓冲区空时立即返回 `None`（`timeout` 参数为 API 兼容性保留但无效）
- 使用 `threading.Lock` 保护头尾指针的读写
- `close()` 关闭并释放 mmap

##### 环形缓冲区布局

```
┌────────────────────────────────────────────────────────┐
│                    mmap (total_size)                     │
├────────────┬───────────────────────────────────────────┤
│   Header   │              Slots                         │
│  (8 bytes) │                                           │
├──────┬─────┼──────┬──────┬──────┬─────┬──────┬─────────┤
│ Head │ Tail│Slot 0│Slot 1│ ...  │     │Slot N-1│       │
│(4B)  │(4B) │      │      │      │     │        │       │
└──────┴─────┴──────┴──────┴──────┴─────┴──────┴─────────┘
```

每个槽位结构：
```
┌──────────────┬──────────────────────────┐
│ Length (4B)  │ Pickled Message Data     │
│              │ (slot_size - 4 bytes)    │
└──────────────┴──────────────────────────┘
```

#### 两种通道对比

| 特性 | NormalChannel | HighSpeedChannel |
|------|--------------|-----------------|
| 后端 | `queue.Queue` / `multiprocessing.Queue` | `mmap` 环形缓冲区 |
| 延迟 | ~ms 级 | ~μs 级 |
| 跨进程 | ✅ 支持（`cross_process=True`） | ❌ 仅同进程 |
| 负载大小限制 | 无限制 | 预分配槽位大小限制（默认 1020B 可用） |
| 序列化 | 跨进程时需 pickle | 始终 pickle + zero-copy `memoryview` |
| 阻塞 send | ❌ 队列满返回 False | ❌ 缓冲区满返回 False |
| 阻塞 recv | ✅ 支持 | ❌ 非阻塞 |
| 适用场景 | 跨进程、大负载、需要阻塞等待 | 同进程、小负载、极低延迟 |

---

### 3.4 ComponentRegistry

**文件**：`framework/registry.py`

管理组件的生命周期：注册、实例化、发现。

#### 构造方法

```python
def __init__(self) -> None
```

无参数。内部维护两个字典：
- `self._components: Dict[str, BaseComponent]` — 已创建的实例
- `self._class_paths: Dict[str, str]` — 名称到类路径的映射

#### 方法

##### `register_instance(name, component) -> None`

注册一个已存在的组件实例。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 组件名称 |
| `component` | `BaseComponent` | 已实例化的组件对象 |

使用场景：手动创建组件后注册到注册表。

##### `register_class(name, class_path) -> None`

注册组件类路径（延迟实例化）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 组件名称 |
| `class_path` | `str` | 类路径，如 `"features.file_reader.FileReader"` |

使用场景：从配置文件加载时，先注册类路径，后续按需实例化。

##### `create(name, **params) -> Optional[BaseComponent]`

根据名称和参数实例化组件。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 已注册的组件名称 |
| `**params` | `Any` | 传递给组件构造函数的参数 |

**返回值**：创建的组件实例，失败返回 `None`。

行为：
1. 查找注册的类路径
2. 使用 `importlib.import_module()` 动态导入模块
3. 通过 `getattr()` 获取类
4. 用 `cls(**params)` 实例化
5. 存储到 `_components` 字典并返回

##### `get(name) -> Optional[BaseComponent]`

获取已注册的组件实例。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 组件名称 |

##### `list_components() -> List[str]`

列出所有已注册的组件名称。

##### `unregister(name) -> None`

注销并清理组件。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 组件名称 |

行为：若组件处于运行状态（`is_running == True`），调用 `component.on_stop()`。

##### `clear() -> None`

移除所有组件和类路径注册。

#### 注册类路径 vs 注册实例的区别

| | `register_class` | `register_instance` |
|--|-----------------|-------------------|
| 注册内容 | 类路径字符串 | 已创建的实例 |
| 实例化时机 | 调用 `create()` 时 | 注册前已实例化 |
| 参数传递 | `create()` 时传入 | 构造时已确定 |
| 适用场景 | 配置文件驱动、延迟加载 | 手动构建、需要自定义初始化 |

---

### 3.5 ObjectPool

**文件**：`framework/pool.py`

管理可复用的组件实例，避免频繁创建/销毁的开销。

#### 构造方法

```python
def __init__(
    self,
    factory: Callable[[], Any],
    max_size: int = 10,
    name: str = "default",
    teardown: Callable[[Any], None] | None = None,
) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `factory` | `Callable[[], Any]` | — | 创建新实例的工厂函数（无参数） |
| `max_size` | `int` | `10` | 池中可保留的最大空闲实例数 |
| `name` | `str` | `"default"` | 池名称（用于日志标识） |
| `teardown` | `Optional[Callable[[Any], None]]` | `None` | 自定义清理回调，实例被丢弃时调用 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `size` | `int` | 池的总实例数（空闲 + 使用中） |
| `idle_count` | `int` | 池中空闲可获取的实例数 |

#### 方法

##### `acquire(timeout=None) -> Any`

从池中获取一个实例。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout` | `Optional[float]` | `None` | 超时秒数，无可用实例且达上限时等待此时间，超时抛出 `TimeoutError` |

行为：
- 优先返回池中已有的空闲实例
- 池为空且未达 `max_size` 时调用 `factory()` 创建新实例
- 池已满且无空闲实例时，阻塞等待 `timeout` 秒，超时抛出 `TimeoutError`
- `_in_use` 计数器 +1
- 线程安全（使用 `RLock` + `Condition`，避免死锁）

##### `release(instance) -> None`

将使用完的实例归还到池中。

| 参数 | 类型 | 说明 |
|------|------|------|
| `instance` | `Any` | 要归还的实例（`None` 会被静默忽略） |

行为：
- `_in_use` 计数器 -1
- 若池中空闲数未达 `max_size`，将实例放回池中
- 若池已满，丢弃实例并尝试清理：
  1. 调用 `teardown` 回调（若提供）
  2. 否则调用实例的 `close()` 或 `shutdown()` 方法（若存在）
  3. 清理异常被记录日志，不影响其他操作
- 线程安全

##### `shrink(target_size=0) -> int`

缩减池中空闲实例数量。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_size` | `int` | `0` | 目标空闲实例数 |

**返回值**：移除的实例数量。

##### `clear() -> None`

清空池中所有空闲实例（不影响使用中的实例）。

#### 工作流程

```
┌──────────┐   acquire()    ┌──────────────┐   use    ┌──────────┐
│  Object  │ ──────────────▶│   In-Use     │─────────▶│  Client  │
│   Pool   │                │  Instances   │          │  Code    │
│          │◀───────────────│              │◀─────────│          │
└──────────┘   release()    └──────────────┘          └──────────┘
     │
     │  pool empty?
     ▼
  factory() ──▶ create new instance
```

#### 适用场景

- 组件创建开销大（如连接数据库、加载模型）
- 高并发下频繁创建/销毁对象
- 需要控制最大并发实例数

---

### 3.6 ParamCache

**文件**：`framework/cache.py`

基于参数哈希的记忆化缓存。相同参数 → 直接返回缓存结果。

#### 构造方法

```python
def __init__(self, ttl: Optional[float] = None, max_size: int = 1000) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ttl` | `Optional[float]` | `None` | 缓存条目存活时间（秒），`None` 表示永不过期 |
| `max_size` | `int` | `1000` | 最大缓存条目数 |

#### 方法

##### `get(params) -> Optional[Any]`

根据参数获取缓存结果。

| 参数 | 类型 | 说明 |
|------|------|------|
| `params` | `Dict[str, Any]` | 参数字典 |

**返回值**：缓存的结果，未命中或已过期返回 `None`。

键生成机制：
1. 使用 `json.dumps(params, sort_keys=True, default=str)` 序列化参数
2. 对序列化结果计算 SHA256 哈希值作为缓存键
3. 若参数不可序列化，降级为 `repr(params)`

##### `set(params, result) -> None`

缓存参数对应的结果。

| 参数 | 类型 | 说明 |
|------|------|------|
| `params` | `Dict[str, Any]` | 参数字典 |
| `result` | `Any` | 要缓存的结果 |

行为：
- 若缓存已满且键不在缓存中，淘汰最旧的条目（LRU 策略）
- 存储 `(result, time.time())` 元组

##### `invalidate(params) -> bool`

使指定参数的缓存条目失效。

| 参数 | 类型 | 说明 |
|------|------|------|
| `params` | `Dict[str, Any]` | 参数字典 |

**返回值**：`True` 表示成功删除了条目，`False` 表示条目不存在。

##### `clear() -> None`

清空所有缓存，重置命中/未命中计数器。

##### `stats() -> Dict[str, Any]`

获取缓存统计信息。

**返回值格式**：
```python
{
    "hits": 150,          # 命中次数
    "misses": 50,         # 未命中次数
    "hit_rate": 0.75,     # 命中率 (hits / total)
    "size": 200,          # 当前缓存条目数
    "max_size": 1000      # 最大容量
}
```

#### TTL 过期策略

- 每次 `get()` 时检查：`time.time() - timestamp > ttl` 则视为过期
- 过期条目在 `get()` 时立即删除（惰性删除）
- `ttl=None` 时永不过期

#### LRU 淘汰策略

- 当缓存达到 `max_size` 且新键不在缓存中时触发
- 选择 `timestamp` 最小的条目（最久未更新）进行淘汰

#### 适用场景

- 计算密集型操作的重复调用
- 相同参数产生相同结果的纯函数
- 需要控制缓存大小和过期时间的场景

---

### 3.7 SnapshotManager

**文件**：`framework/snapshot.py`

管理状态快照，用于中断恢复。

#### 构造方法

```python
def __init__(self, storage_dir: Optional[str] = None) -> None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `storage_dir` | `Optional[str]` | `None` | 快照存储目录，默认 `{cwd}/.snapshots` |

行为：自动创建存储目录。

#### 方法

##### `capture(snapshot_id, components=None, pending_messages=None, cache_data=None, metadata=None) -> str`

创建内存快照。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `snapshot_id` | `str` | — | 快照唯一标识 |
| `components` | `Optional[Dict[str, Any]]` | `None` | 组件状态字典（如各组件的 params） |
| `pending_messages` | `Optional[list]` | `None` | 待处理消息列表 |
| `cache_data` | `Optional[Dict[str, Any]]` | `None` | 缓存数据 |
| `metadata` | `Optional[Dict[str, Any]]` | `None` | 自定义元数据 |

**返回值**：快照 ID。

快照数据结构：
```python
{
    "components": {...},              # 组件状态
    "pending_messages": [...],        # 待处理消息
    "cache_data": {...},              # 缓存数据
    "metadata": {
        "timestamp": "2026-04-08T10:30:00",
        "framework_version": "2.0.0",
        # ... 自定义 metadata 合并到此处
    }
}
```

##### `restore(snapshot_id) -> Optional[Dict[str, Any]]`

恢复快照。

| 参数 | 类型 | 说明 |
|------|------|------|
| `snapshot_id` | `str` | 快照 ID |

**返回值**：快照数据字典，不存在则返回 `None`。

行为：
1. 先在内存中查找
2. 若内存中不存在，尝试从磁盘加载（调用 `load()`）

##### `list_snapshots() -> Dict[str, Dict[str, Any]]`

列出所有可用快照（内存 + 磁盘）。

**返回值格式**：
```python
{
    "snapshot_id": {
        "timestamp": "2026-04-08T10:30:00",
        "component_count": 3,
        "has_messages": True,
        "has_cache": False
    }
}
```

##### `delete(snapshot_id) -> bool`

删除快照（内存 + 磁盘）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `snapshot_id` | `str` | 快照 ID |

**返回值**：`True` 表示至少删除了一个（内存或磁盘），`False` 表示不存在。

##### `persist(snapshot_id) -> bool`

将内存快照持久化到磁盘 JSON 文件。

| 参数 | 类型 | 说明 |
|------|------|------|
| `snapshot_id` | `str` | 快照 ID |

**返回值**：`True` 表示持久化成功，`False` 表示快照不存在或写入失败。

文件路径：`{storage_dir}/{snapshot_id}.json`

##### `load(snapshot_id) -> Optional[Dict[str, Any]]`

从磁盘加载快照到内存。

| 参数 | 类型 | 说明 |
|------|------|------|
| `snapshot_id` | `str` | 快照 ID |

**返回值**：快照数据，文件不存在或解析失败返回 `None`。

#### 中断恢复流程

```
运行中 ──▶ capture("snap_001", ...) ──▶ persist("snap_001")
   │                                         │
   │  (中断)                                  │  磁盘快照
   ▼                                         ▼
恢复 ◀──────── restore("snap_001") ◀────── load("snap_001")
   │
   ├── 恢复 components 状态
   ├── 重放 pending_messages
   └── 恢复 cache_data
```

---

### 3.8 config_loader

**文件**：`framework/config_loader.py`

#### `load_framework_config(config_path) -> Dict[str, Any]`

从 JSON 文件加载框架配置。

| 参数 | 类型 | 说明 |
|------|------|------|
| `config_path` | `str` | JSON 配置文件路径 |

**返回值**：
```python
{
    "registry": ComponentRegistry,    # 已注册类路径的注册表
    "components_cfg": [...],          # 原始组件配置列表
    "bus_config": {
        "default_channel": ChannelType  # 默认通道类型
    }
}
```

行为：
1. 读取并解析 JSON
2. 为每个组件调用 `registry.register_class(name, class_path)`
3. 解析 `bus.default_channel`：`"highspeed"` → `ChannelType.HIGH_SPEED`，其他 → `ChannelType.NORMAL`
4. 返回包含注册表、组件配置和总线配置的字典

---

## 4. 完整示例

### 示例 1：基础发布/订阅

创建两个组件，一个发布计数，一个接收并打印。

```python
"""示例1：基础发布/订阅"""
import time
import threading
from framework.bus import MessageBus
from framework.channels.base import ChannelType, Message
from framework.interfaces import BaseComponent
from typing import Any


class Counter(BaseComponent):
    """计数器组件：每秒发布一个计数值。"""

    name = "counter"

    def on_start(self) -> None:
        self._count = 0
        # 订阅 start 信号
        self._bus.subscribe("counter.start", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        self._count += 1
        # 发布计数值
        self._bus.publish(
            "counter.value",
            payload={"count": self._count},
            sender=self.name,
        )
        return self._count


class Logger(BaseComponent):
    """日志组件：接收计数值并打印。"""

    name = "logger"

    def on_start(self) -> None:
        self._bus.subscribe("counter.value", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        print(f"[Logger] 收到计数: {message.payload}")
        return {"logged": True}


def main():
    # 创建总线
    bus = MessageBus(default_channel=ChannelType.HIGH_SPEED)

    # 创建并注册组件
    counter = Counter()
    logger = Logger()
    bus.register_component(counter)
    bus.register_component(logger)

    # 启动

    # 触发计数器
    for _ in range(3):
        bus.publish("counter.start", payload={"trigger": True}, sender="main")
        time.sleep(0.1)

    # 等待消息处理
    time.sleep(0.5)

    # 清理
    bus.shutdown()


if __name__ == "__main__":
    main()
```

---

### 示例 2：使用对象池 + 缓存

展示 `ObjectPool` 和 `ParamCache` 的配合使用。

```python
"""示例2：对象池 + 缓存"""
import time
from framework.pool import ObjectPool
from framework.cache import ParamCache
from framework.interfaces import BaseComponent
from framework.channels.base import Message
from typing import Any


class ExpensiveWorker(BaseComponent):
    """模拟高开销计算组件。使用对象池复用实例，使用缓存避免重复计算。"""

    name = "expensive_worker"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.cache = ParamCache(ttl=60.0, max_size=100)

    def on_start(self) -> None:
        self._bus.subscribe("compute.request", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        params = message.payload if isinstance(message.payload, dict) else {}

        # 先查缓存
        cached = self.cache.get(params)
        if cached is not None:
            print(f"[Worker] 缓存命中: {params}")
            return {"result": cached, "from_cache": True}

        # 模拟高开销计算
        result = sum(i * i for i in range(params.get("n", 1000)))
        print(f"[Worker] 计算完成: n={params.get('n')}")

        # 写入缓存
        self.cache.set(params, result)
        return {"result": result, "from_cache": False}


def main():
    # 创建对象池：复用 ExpensiveWorker 实例
    def factory():
        return ExpensiveWorker()

    pool = ObjectPool(factory=factory, max_size=5, name="worker_pool")

    # 获取实例
    worker1 = pool.acquire()
    worker2 = pool.acquire()

    print(f"池大小: {pool.size}, 空闲: {pool.idle_count}")

    # 使用组件
    from framework.bus import MessageBus
    from framework.channels.base import Message as Msg

    bus = MessageBus()
    bus.register_component(worker1)
    bus.register_component(worker2)

    # 发布计算请求（相同参数，第二次命中缓存）
    bus.publish("compute.request", payload={"n": 100}, sender="main")
    time.sleep(0.1)
    bus.publish("compute.request", payload={"n": 100}, sender="main")
    time.sleep(0.1)

    # 查看缓存统计
    stats = worker1.cache.stats()
    print(f"缓存统计: {stats}")

    # 归还实例
    pool.release(worker1)
    pool.release(worker2)

    print(f"池大小: {pool.size}, 空闲: {pool.idle_count}")

    # 缩容
    removed = pool.shrink(target_size=1)
    print(f"移除空闲实例数: {removed}")
    print(f"缩容后空闲: {pool.idle_count}")

    bus.shutdown()


if __name__ == "__main__":
    main()
```

---

### 示例 3：状态快照与恢复

展示 `SnapshotManager` 的 capture/persist/load 流程。

```python
"""示例3：状态快照与恢复"""
import os
import json
import shutil
from framework.snapshot import SnapshotManager
from framework.cache import ParamCache


def main():
    # 清理旧的快照目录
    snap_dir = os.path.join(os.getcwd(), ".snapshot_demo")
    if os.path.exists(snap_dir):
        shutil.rmtree(snap_dir)

    # 创建快照管理器
    sm = SnapshotManager(storage_dir=snap_dir)

    # 模拟组件状态
    components = {
        "worker1": {"processed": 150, "status": "running"},
        "worker2": {"processed": 89, "status": "idle"},
    }

    # 模拟待处理消息
    pending = [
        {"topic": "data.process", "payload": {"id": 1}},
        {"topic": "data.process", "payload": {"id": 2}},
        {"topic": "data.process", "payload": {"id": 3}},
    ]

    # 模拟缓存数据
    cache_data = {
        "key_abc": "cached_value_1",
        "key_def": "cached_value_2",
    }

    # 创建快照
    sm.capture(
        snapshot_id="snap_001",
        components=components,
        pending_messages=pending,
        cache_data=cache_data,
        metadata={"stage": "processing", "batch": 3},
    )
    print("已创建快照: snap_001")

    # 持久化到磁盘
    success = sm.persist("snap_001")
    print(f"持久化{'成功' if success else '失败'}")

    # 列出所有快照
    snapshots = sm.list_snapshots()
    for sid, info in snapshots.items():
        print(f"  {sid}: {info}")

    # 模拟程序重启 —— 从磁盘加载快照
    sm2 = SnapshotManager(storage_dir=snap_dir)
    restored = sm2.restore("snap_001")

    if restored:
        print(f"\n恢复快照:")
        print(f"  组件状态: {json.dumps(restored['components'], indent=2, ensure_ascii=False)}")
        print(f"  待处理消息数: {len(restored['pending_messages'])}")
        print(f"  缓存条目数: {len(restored['cache_data'])}")
        print(f"  元数据: {restored['metadata']}")

    # 清理
    deleted = sm2.delete("snap_001")
    print(f"\n删除快照: {'成功' if deleted else '不存在'}")

    # 清理快照目录
    shutil.rmtree(snap_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
```

---

### 示例 4：双通道混合使用

同时使用 `NormalChannel` 和 `HighSpeedChannel`，展示何时该用哪种通道。

```python
"""示例4：双通道混合使用"""
import time
from framework.bus import MessageBus
from framework.channels.base import ChannelType, Message
from framework.interfaces import BaseComponent
from typing import Any


class SensorReader(BaseComponent):
    """模拟传感器读取组件：高频小数据，使用高速通道。"""

    name = "sensor_reader"

    def on_start(self) -> None:
        self._bus.subscribe("sensor.start", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        # 模拟传感器数据（小负载，适合高速通道）
        data = {"temperature": 23.5, "humidity": 65.0}
        self._bus.publish(
            "sensor.data",
            payload=data,
            sender=self.name,
            channel_type=ChannelType.HIGH_SPEED,  # 指定高速通道
        )
        return data


class AlertSystem(BaseComponent):
    """告警系统：接收传感器数据并检查阈值。"""

    name = "alert_system"

    def on_start(self) -> None:
        self._bus.subscribe("sensor.data", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        data = message.payload
        if isinstance(data, dict):
            temp = data.get("temperature", 0)
            if temp > 30:
                print(f"[Alert] 温度过高: {temp}")
                self._bus.publish(
                    "alert.triggered",
                    payload={"type": "high_temp", "value": temp},
                    sender=self.name,
                    channel_type=ChannelType.NORMAL,  # 告警使用普通通道（可靠性优先）
                )
        return {"checked": True}


class FileLogger(BaseComponent):
    """文件日志组件：大负载，使用普通通道。"""

    name = "file_logger"

    def on_start(self) -> None:
        self._bus.subscribe("alert.triggered", self.handle_message)

    def handle_message(self, message: Message) -> Any:
        payload = message.payload
        # 模拟写入大量日志数据（普通通道无大小限制）
        log_entry = f"[{message.timestamp}] ALERT: {payload}"
        print(f"[FileLogger] 写入日志: {log_entry}")
        return {"logged": True}


def main():
    # 总线默认使用高速通道
    bus = MessageBus(default_channel=ChannelType.HIGH_SPEED)

    # 注册组件
    sensor = SensorReader()
    alert = AlertSystem()
    logger = FileLogger()

    bus.register_component(sensor)
    bus.register_component(alert)
    bus.register_component(logger)


    # 触发传感器读取
    bus.publish("sensor.start", payload={"mode": "continuous"}, sender="main")
    time.sleep(0.2)

    # 查看通道信息
    sensor_channel = bus.get_channel("sensor.data", ChannelType.HIGH_SPEED)
    alert_channel = bus.get_channel("alert.triggered", ChannelType.NORMAL)

    print(f"传感器通道类型: {sensor_channel.channel_type}")
    print(f"告警通道类型: {alert_channel.channel_type}")

    bus.shutdown()


if __name__ == "__main__":
    main()
```

---

### 示例 5：自定义组件（文件处理）

从零编写一个完整的 `BaseComponent` 子类，包含订阅、发布、参数提取、生命周期钩子。

```python
"""示例5：自定义组件 — 文件处理器"""
import os
import json
import logging
from typing import Any, Dict, Optional
from framework.interfaces import BaseComponent
from framework.channels.base import Message
from framework.cache import ParamCache

log = logging.getLogger(__name__)


class FileProcessor(BaseComponent):
    """文件处理组件：读取文件、转换格式、发布结果。

    订阅主题:
        - "process.file": 触发文件处理

    发布主题:
        - "process.result": 处理完成，包含结果数据

    参数:
        - input_dir: 输入目录（默认: "."）
        - output_key: 输出键名（默认: "content"）
        - transform: 转换方式，"upper"/"lower"/"lines"/"json"（默认: "upper"）
        - cache_enabled: 是否启用缓存（默认: True）
    """

    name = "file_processor"

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        # 提取参数并设置默认值
        self.input_dir: str = params.get("input_dir", ".")
        self.output_key: str = params.get("output_key", "content")
        self.transform: str = params.get("transform", "upper")
        self.cache_enabled: bool = params.get("cache_enabled", True)

        # 内部状态
        self._processed_count: int = 0
        self._error_count: int = 0
        self._cache: Optional[ParamCache] = None

    def on_start(self) -> None:
        """组件启动时：初始化缓存，订阅主题。"""
        if self.cache_enabled:
            self._cache = ParamCache(ttl=300.0, max_size=500)

        self._bus.subscribe("process.file", self.handle_message)
        log.info("[%s] 已启动, input_dir=%s, transform=%s",
                 self.name, self.input_dir, self.transform)

    def on_stop(self) -> None:
        """组件停止时：输出统计信息。"""
        log.info("[%s] 已停止, 处理=%d, 错误=%d",
                 self.name, self._processed_count, self._error_count)

    def handle_message(self, message: Message) -> Any:
        """处理文件请求消息。"""
        payload = message.payload
        if not isinstance(payload, dict):
            self._error_count += 1
            return {"error": "payload must be a dict"}

        filename = payload.get("filename")
        if not filename:
            self._error_count += 1
            return {"error": "missing 'filename' in payload"}

        # 构建完整路径
        filepath = os.path.join(self.input_dir, filename)
        if not os.path.exists(filepath):
            self._error_count += 1
            return {"error": f"file not found: {filepath}"}

        # 构建缓存键参数
        cache_params = {"filepath": filepath, "transform": self.transform}

        # 检查缓存
        if self._cache:
            cached = self._cache.get(cache_params)
            if cached is not None:
                self._processed_count += 1
                result = {self.output_key: cached, "from_cache": True}
                self._publish_result(result, filename)
                return result

        # 读取并转换文件
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            result_data = self._transform(content)
        except Exception as e:
            self._error_count += 1
            return {"error": str(e)}

        # 写入缓存
        if self._cache:
            self._cache.set(cache_params, result_data)

        self._processed_count += 1
        result = {self.output_key: result_data, "from_cache": False}
        self._publish_result(result, filename)
        return result

    def _transform(self, content: str) -> str:
        """根据配置转换文件内容。"""
        if self.transform == "upper":
            return content.upper()
        elif self.transform == "lower":
            return content.lower()
        elif self.transform == "lines":
            lines = content.strip().split("\n")
            return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
        elif self.transform == "json":
            return json.dumps({"content": content, "length": len(content)},
                              ensure_ascii=False, indent=2)
        return content

    def _publish_result(self, result: Dict[str, Any], filename: str) -> None:
        """发布处理结果到总线。"""
        self._bus.publish(
            "process.result",
            payload={**result, "filename": filename},
            sender=self.name,
        )

    def get_stats(self) -> Dict[str, int]:
        """获取组件统计信息。"""
        return {
            "processed": self._processed_count,
            "errors": self._error_count,
            "cache_stats": self._cache.stats() if self._cache else {},
        }


# ---- 使用示例 ----

def main():
    import time
    from framework.bus import MessageBus
    from framework.channels.base import ChannelType

    logging.basicConfig(level=logging.INFO)

    # 准备测试文件
    with open("test_sample.txt", "w", encoding="utf-8") as f:
        f.write("Hello World\nThis is a test file\nFor the file processor component")

    bus = MessageBus(default_channel=ChannelType.HIGH_SPEED)

    # 创建自定义组件
    processor = FileProcessor(
        input_dir=".",
        output_key="processed_content",
        transform="lines",
        cache_enabled=True,
    )

    bus.register_component(processor)

    # 第一次处理（缓存未命中）
    bus.publish(
        "process.file",
        payload={"filename": "test_sample.txt"},
        sender="main",
    )
    time.sleep(0.2)

    # 第二次处理（相同参数，缓存命中）
    bus.publish(
        "process.file",
        payload={"filename": "test_sample.txt"},
        sender="main",
    )
    time.sleep(0.2)

    # 使用不同的转换方式（缓存未命中）
    processor2 = FileProcessor(
        input_dir=".",
        transform="json",
        cache_enabled=True,
    )
    bus.register_component(processor2)

    bus.publish(
        "process.file",
        payload={"filename": "test_sample.txt"},
        sender="main",
    )
    time.sleep(0.2)

    # 查看统计
    print(f"\n组件统计: {processor.get_stats()}")

    # 清理
    bus.shutdown()

    # 清理测试文件
    os.remove("test_sample.txt")


if __name__ == "__main__":
    main()
```

### 示例6：三种投递后端对比

框架的 `MessageBus` 支持三种消息投递后端，适用于不同场景。

```python
"""示例6：三种投递后端 — thread / process / asyncio"""
from __future__ import annotations
import time
import asyncio
import logging
from framework.bus import MessageBus
from framework.channels.base import ChannelType, Message

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def make_handler(label: str):
    """返回一个记录日志的处理器。"""
    def handler(message: Message) -> None:
        print(f"[{label}] 收到 topic={message.topic} payload={message.payload}")
    return handler


def make_async_handler(label: str):
    """返回一个异步处理器。"""
    async def handler(message: Message) -> None:
        print(f"[async {label}] 收到 topic={message.topic} payload={message.payload}")
        await asyncio.sleep(0.01)  # 模拟异步 I/O
    return handler


# ---- 1. Thread 模式（默认，I/O 密集型） ----
def test_thread():
    print("\n=== Thread 后端 ===")
    bus = MessageBus(
        default_channel=ChannelType.HIGH_SPEED,
        delivery_mode="thread",
        max_workers=4,
    )
    bus.subscribe("data.event", make_handler("订阅者A"))
    bus.subscribe("data.event", make_handler("订阅者B"))
    bus.publish("data.event", payload={"value": 42}, sender="main")
    time.sleep(0.3)
    bus.shutdown()


# ---- 2. Process 模式（CPU 密集型 / 隔离） ----
def test_process():
    print("\n=== Process 后端 ===")
    bus = MessageBus(
        default_channel=ChannelType.NORMAL,
        delivery_mode="process",
        max_workers=2,
    )
    bus.subscribe(
        "compute.task",
        make_handler("process-worker"),
        handler_info={
            "module": "features.file_reader",
            "class_name": "FileReader",
            "method_name": "handle_message",
            "params": {"path": "sample.txt"},
        },
    )
    bus.publish("compute.task", payload={"compute": True}, sender="main")
    time.sleep(1.0)
    bus.shutdown()


# ---- 3. Asyncio 模式（异步原生） ----
def test_asyncio():
    print("\n=== Asyncio 后端 ===")
    bus = MessageBus(
        default_channel=ChannelType.HIGH_SPEED,
        delivery_mode="asyncio",
    )
    bus.subscribe("io.event", make_async_handler("async-A"))
    bus.subscribe("io.event", make_handler("sync-fallback"))
    bus.publish("io.event", payload={"async": True}, sender="main")
    time.sleep(0.5)
    bus.shutdown()


if __name__ == "__main__":
    test_thread()
    test_process()
    test_asyncio()
    print("\n三种投递后端全部运行成功。")
```

#### 如何选择投递后端

| 场景 | 推荐模式 | 原因 |
|------|----------|------|
| 大多数组件 | `"thread"`（默认） | 简单，无需额外配置，I/O 密集型表现良好 |
| CPU 密集计算 | `"process"` | 绕过 GIL，真正多核并行；子进程崩溃不影响主进程 |
| 大量异步 I/O | `"asyncio"` | 与 aiohttp/asyncpg 等异步库无缝集成 |

#### Process 模式注意事项

1. **组件必须可重建**：子进程通过 `module + class_name + params` 重新实例化组件，`__init__` 不能使用不可序列化的参数
2. **必须提供 `handler_info`**：`subscribe()` 时需传入组件重建信息字典
3. **跨进程通信搭配 NormalChannel**：建议 `default_channel=ChannelType.NORMAL`
4. **子进程异常不传播**：通过 `error_callback` 记录日志，主进程不受影响

---

## 5. 框架优势与局限性

### 优势

1. **零外部依赖** — 仅使用 Python 标准库，无 `pip install` 需求，部署极简
2. **三投递后端** — thread / process / asyncio 可根据场景切换，一个总线覆盖所有并发模型
3. **双通道架构** — HighSpeedChannel（mmap 环形缓冲区，μs 级）+ NormalChannel（queue，支持跨进程），按需选择
4. **组件完全解耦** — 发布/订阅模型，组件不知道彼此的存在，框架也不知道哪些组件会接入
5. **性能层内置** — ObjectPool（实例复用，支持 teardown）、ParamCache（同参缓存，O(1) LRU）、SnapshotManager（中断恢复）开箱即用
6. **动态组件加载** — 通过 `importlib` 从配置字符串路径动态实例化，无需硬编码
7. **线程安全设计** — 所有共享状态有锁保护，UI 调用通过 `after()` 编组到主线程
8. **健壮的错误处理** — 全面的异常捕获和日志记录，单个处理器异常不影响其他处理器
9. **自动化生命周期管理** — 组件注册/注销时自动调用 `attach_bus`/`detach_bus`，确保资源正确清理
10. **进程模式组件缓存** — 子进程中使用 LRU 缓存复用组件实例，避免重复实例化开销

### 局限性

1. **Python GIL 限制** — thread 模式下 CPU 密集型任务不会真正并行，需用 process 模式绕过
2. **HighSpeedChannel 仅限同进程** — mmap 不支持跨进程，跨进程必须用 NormalChannel
3. **环形缓冲区有容量上限** — 默认 64 槽 × 1024 字节，写满时 send() 返回 False，需应用层处理背压
4. **无消息持久化** — 消息仅在内存/共享内存中，进程重启即丢失（SnapshotManager 可部分缓解）
5. **无内置消息确认** — 发布后不保证投递成功，需应用层自行实现 ACK 机制
6. **无安全认证** — 无身份验证或授权机制，不适合多租户环境
7. **无可视化监控** — 无内置仪表板或指标导出，需自行集成

### 与同类型框架对比

| 维度 | 本框架 | PyZMQ | RabbitMQ (pika) | Redis Pub/Sub | Celery |
|------|--------|-------|------------------|---------------|--------|
| **外部依赖** | 无（stdlib） | pyzmq | pika + RabbitMQ 服务 | redis-py + Redis 服务 | celery + broker |
| **部署复杂度** | 零配置 | 安装 C 库 | 需运行消息代理 | 需运行 Redis | 需运行 broker |
| **通信模型** | pub/sub | pub/sub + REQ/REP | AMQP 队列 | pub/sub | 任务队列 |
| **进程间通信** | NormalChannel（multiprocessing.Queue） | ✅（原生） | ✅（网络） | ✅（网络） | ✅（网络） |
| **低延迟通道** | mmap 环形缓冲区 | inproc IPC | ❌ | ❌ | ❌ |
| **投递后端** | thread / process / asyncio（策略模式） | IOLoop | 同步/异步/Tornado | 同步/asyncio | 多 worker |
| **组件动态发现** | ✅（importlib + ComponentRegistry） | ❌ | ❌ | ❌ | ✅（自动发现） |
| **对象池** | ✅ 内置（teardown 支持，超时获取） | ❌ | ❌ | ❌ | ❌ |
| **参数缓存** | ✅ 内置（O(1) LRU + TTL） | ❌ | ❌ | ❌ | ✅（backend cache） |
| **状态快照** | ✅ 内置（磁盘持久化） | ❌ | ❌ | ❌ | ❌ |
| **消息持久化** | ❌（仅磁盘快照） | ❌ | ✅（持久化队列） | ❌ | ✅（结果后端） |
| **错误处理** | ✅ 全面异常捕获 + 日志记录 | ✅ | ✅ | ⚠️（fire-and-forget） | ✅（重试 + 死信队列） |
| **生命周期管理** | ✅ 自动化（attach/detach bus） | ❌ | ❌ | ❌ | ✅（worker 生命周期） |
| **进程模式组件缓存** | ✅ LRU 缓存复用实例 | ❌ | ❌ | ❌ | ❌ |
| **UI 集成** | ✅ Tkinter 线程安全编组 | ❌ | ❌ | ❌ | ❌ |
| **适用场景** | 单机组件通信，快速原型，教学 | 分布式系统，高性能网络通信 | 企业级消息队列，微服务 | 轻量级事件通知，缓存失效 | 分布式任务调度 |

**何时选择本框架**：
- 单机应用，需要组件间解耦通信
- 不想引入外部依赖或中间件
- 需要同时支持多种并发模型
- 快速原型开发或教学场景
- 需要内置的性能优化（缓存、对象池、快照）

**何时选择其他方案**：
- 分布式部署 → PyZMQ / RabbitMQ
- 需要消息保证投递 → RabbitMQ
- 大规模任务调度 → Celery
- 需要持久化消息队列 → RabbitMQ / Redis Streams
- 需要复杂的路由规则 → RabbitMQ（topic/fanout/headers exchange）
