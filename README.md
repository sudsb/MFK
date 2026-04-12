# MessageBus Component Framework (v2.1)

一个基于通信的组件框架，组件通过MessageBus进行零耦合通信。组件只需声明"能做什么"和"关心什么"，不需要知道对方的存在。

## 特性

- **纯Python标准库** - 无外部依赖
- **零耦合架构** - 组件互不感知，通过能力和事件通信
- **动态组件发现** - 运行时注册组件
- **多种通信通道** - 支持高性能和跨进程通信
- **性能优化层** - 对象池、参数缓存、状态快照
- **跨进程支持** - 进程隔离和线程安全
- **策略化交付后端** - 线程/进程/异步三种投递模式
- **双模式注册表** - `thread_safe=True`（默认，线程安全）和 `thread_safe=False`（无锁，高性能），通过 `_locked()` 上下文管理器同一份代码自动切换
- **健壮的错误处理** - 全面的异常捕获和日志记录
- **自动化生命周期管理** - 组件注册/注销自动处理

## 快速开始

### 环境要求

- Python 3.11+
- 操作系统：支持mmap（Windows/Linux/macOS）

### 交互式配置生成

框架提供两个交互式 CLI 工具，帮助你快速上手：

**生成配置文件**：
```bash
python generate_config.py
```
通过问答方式生成 `config.json`，支持 `--output` 指定输出路径，`--dry-run` 预览不写入。

**生成组件骨架代码**：
```bash
python generate_component.py
```
通过问答生成 `BaseComponent` 子类 Python 文件及对应 JSON 配置片段，支持 `-d` 指定输出目录，`--dry-run` 预览。

### 运行Pipeline模式

```bash
python test_config.py
```

这将：
1. 加载 `config.json` 配置
2. 创建MessageBus实例
3. 动态注册组件
4. 执行文件读取和打印管道

### 运行UI演示

```bash
python main.py
```

启动Tkinter双屏通信演示应用。

## 架构概览

```
main.py                    → Tkinter UI 入口（双屏演示，非配置驱动）
test_config.py             → 配置驱动管道：加载 config.json → 创建总线 + 组件
generate_config.py         → 交互式 CLI：通过问答生成 config.json
generate_component.py      → 交互式 CLI：生成 BaseComponent 子类代码 + JSON 配置片段
config.json               → 组件定义 + 总线配置（由 config_loader 使用，main.py 不使用）
framework/
  __init__.py             → 公共API导出
  interfaces.py           → BaseComponent ABC (含自动化生命周期管理)
  bus.py                  → MessageBus：发布/订阅路由，DeliveryBackend交付后端(策略模式)
  config_loader.py        → JSON → ComponentRegistry + 总线配置
  registry.py             → ComponentRegistry：动态实例化
  pool.py                 → ObjectPool：组件实例重用池 (含 teardown 支持)
  cache.py                → ParamCache：基于O(1) OrderedDict的参数哈希缓存
  snapshot.py             → SnapshotManager：状态保存/恢复
  channels/
    base.py               → Channel ABC + Message数据类 + ChannelType枚举
    normal.py             → NormalChannel：queue.Queue / multiprocessing.Queue
    highspeed.py          → HighSpeedChannel：mmap环形缓冲区
features/
  file_reader.py          → FileReader：读取文件，发布到总线
  printer.py              → ConsolePrinter：订阅数据，打印
  screen1.py/screen2.py   → UI屏幕组件
  ui_app.py               → Tkinter UI应用
```

## 投递后端 (Delivery Backends)

`MessageBus` 支持三种投递模式，通过 `delivery_mode` 参数控制：

| 模式 | 后端 | 适用场景 | 注意事项 |
|------|------|----------|----------|
| `"thread"` (默认) | `ThreadPoolExecutor` | I/O 密集型处理器 | GIL 限制 CPU 并行 |
| `"process"` | `multiprocessing.Pool` 子进程 | CPU 密集型，隔离 | **需要 `handler_info`** 或回退到线程 |
| `"asyncio"` | 独立事件循环线程 | 异步原生组件 | 协程直接 await；同步通过 `run_in_executor` |

### 进程模式 `handler_info` (关键)

进程投递会在子进程中重新实例化组件。`subscribe()` 必须包含：

```python
bus.subscribe("topic", handler, handler_info={
    "module": "features.file_reader",   # 模块路径
    "class_name": "FileReader",          # 类名
    "method_name": "handle_message",     # 方法名
    "params": {"path": "data.txt"}       # __init__ 参数
})
```

缺少 `handler_info` 会回退到线程投递并输出警告。详见 `docs/process_delivery.md`。

### 跨进程规则

- `HighSpeedChannel` (mmap) **不跨进程安全**。跨进程请使用 `NormalChannel`。
- 进程模式下消息负载必须可 pickle。

## 配置

### Pipeline配置 (config.json)

```json
{
  "components": [
    {
      "name": "reader",
      "class": "features.file_reader.FileReader",
      "params": {
        "path": "sample.txt",
        "output_key": "file_content"
      }
    },
    {
      "name": "printer",
      "class": "features.printer.ConsolePrinter",
      "params": {
        "input_key": "file_content"
      }
    }
  ],
  "bus": {
    "default_channel": "highspeed"
  }
}
```

**注意**：组件的 `capabilities` 和 `interests` 在代码中声明，配置文件中只需指定实例化哪些组件和参数。
```

### 通道类型

| 特性 | NormalChannel | HighSpeedChannel |
|------|---------------|------------------|
| 后端 | queue.Queue / multiprocessing.Queue | mmap环形缓冲区 |
| 延迟 | ~ms | ~μs |
| 跨进程 | ✅ | ❌ (仅同进程) |
| 负载限制 | 无 | 预分配 (默认1024B/槽) |
| 序列化 | pickle (跨进程) | pickle + memoryview零拷贝 |

## 组件开发

### 基本组件

继承 `BaseComponent`，声明 `capabilities` 和 `interests`，实现 `handle_message(message: Message) -> Any`：

```python
from framework.interfaces import BaseComponent
from framework.channels.base import Message

class FileReader(BaseComponent):
    name: str = "file_reader"

    # 声明式：我能做什么，我关心什么
    capabilities = ["file.read"]   # 我提供读取文件的能力
    interests = []                 # 我不关心任何事件

    def __init__(self, **params):
        super().__init__(**params)
        self.path = params.get("path", "sample.txt")

    def handle_message(self, message: Message):
        # 读取文件
        with open(self.path) as f:
            content = f.read()
        # 发出事件，不关心谁接收
        self._bus.emit("data.loaded", {"content": content}, sender=self.name)
        return {"content": content}

class ConsolePrinter(BaseComponent):
    name: str = "console_printer"

    capabilities = []              # 我不提供任何能力
    interests = ["data.loaded"]    # 我关心数据加载完成事件

    def handle_message(self, message: Message):
        print(message.payload)
        return {"printed": True}
```

### 调用能力和发出事件

```python
# 调用能力 - 不关心谁提供
results = self._bus.invoke("file.read", payload={"path": "data.txt"})

# 发出事件 - 不关心谁接收
self._bus.emit("data.loaded", {"key": "value"}, sender=self.name)
```

### 生命周期钩子

- `on_start()` - 框架在 `attach_bus` 时**自动调用**，用于初始化逻辑。此时 `capabilities` 和 `interests` 已自动注册/订阅。
- `on_stop()` - 框架在 `detach_bus` 时**自动调用**，用于清理资源。
- `attach_bus(bus)` - 框架调用，自动注册 capabilities、订阅 interests，然后触发 `on_start`。
- `detach_bus()` - 框架调用，触发 `on_stop`，然后取消注册 capabilities、取消订阅 interests。

## 性能特性

### 对象池 (ObjectPool)

- 组件实例重用，避免创建/销毁开销
- 工厂模式，可配置最大大小
- `acquire()` / `release()` 接口

### 参数缓存 (ParamCache)

- SHA256参数哈希键
- 基于 `collections.OrderedDict` 实现的 **O(1)** 级别 LRU 淘汰驱逐机制
- 适用于确定性计算结果缓存，支持 TTL 过期

### 状态快照 (SnapshotManager)

- 捕获组件状态 + 待处理消息 + 缓存
- 中断恢复支持
- JSON磁盘持久化

## 通信模式 (策略后端)

`MessageBus` 在其底层采用分离式的交付策略模式（DeliveryBackend）：

### 线程模式 (默认)

- `ThreadBackend`: 使用 `ThreadPoolExecutor` 线程池
- 适用于I/O密集型处理器

### 进程模式

- `ProcessBackend`: 使用 `multiprocessing.Pool`
- 为避免大量的反序列化耗时，采用了全局 `_process_component_cache` 机制在子进程中复用被实例化的组件
- 提供真正的隔离和突破 GIL 的 CPU 密集型安全性

### 异步模式

- `AsyncioBackend`: 使用共享事件循环
- 协程处理器通过线程安全方法直接等待
- 同步处理器通过 `loop.run_in_executor` 分派

## UI集成

框架支持Tkinter UI组件集成：

- **线程安全**: UI调用通过 `root.after(0, ...)` 编组到主线程
- **跨屏通信**: 组件通过MessageBus通信
- **生命周期管理**: 组件注册到总线，参与发布/订阅

## 开发约定

- 所有导入相对于项目根目录（根目录无 `__init__.py`）
- 组件参数通过 `self.params` 字典访问
- `config.json` 中的文件路径相对于项目根目录
- 运行时从项目根目录执行

## 稳定性说明

- **UI线程安全**: 不要从总线处理器直接调用Tkinter方法
- **并发安全**: `CapabilityRegistry` 和 `ComponentRegistry` 通过 `_locked()` 上下文管理器实现双模式：默认 `thread_safe=True`（`RLock` 保护，线程安全）和 `thread_safe=False`（无锁，高性能）。`MessageBus` 订阅表和组件字典也有锁保护
- **无锁模式**: 单线程场景可通过 `MessageBus(thread_safe=False)` 获得 ~5-15% 性能提升（详见 `examples/lock_free_example.py`）
- **进程模式**: `subscribe()` 需要 `handler_info` 用于子进程组件重建
- **组件验证**: `registry.create()` 通过importlib实例化，确保类路径正确且 `__init__` 参数可序列化
- **交付后端配置**: 使用 `delivery_mode` 参数选择线程/进程/异步模式
- **错误处理**: 所有异常被捕获并记录日志，不会影响其他处理器
- **组件生命周期**: 注册/注销时自动调用 `attach_bus`/`detach_bus`，确保资源正确清理

## 许可证

MIT License
