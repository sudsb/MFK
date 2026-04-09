# MessageBus Component Framework (v2.0)

一个基于通信的组件框架，组件通过MessageBus进行发布/订阅通信。框架事先不知道将连接哪些组件。

## 特性

- **纯Python标准库** - 无外部依赖
- **动态组件发现** - 运行时注册组件
- **多种通信通道** - 支持高性能和跨进程通信
- **性能优化层** - 对象池、参数缓存、状态快照
- **跨进程支持** - 进程隔离和线程安全

## 快速开始

### 环境要求

- Python 3.11+
- 操作系统：支持mmap（Windows/Linux/macOS）

### 运行Pipeline模式

```bash
python main.py
```

这将：
1. 加载 `config.json` 配置
2. 创建MessageBus实例
3. 动态注册组件
4. 执行文件读取和打印管道

### 运行UI演示

```bash
python main.py  # UI模式
```

启动Tkinter双屏通信演示应用。

## 架构概览

```
main.py                    → 入口点：加载配置，创建总线，注册组件
config.json               → 组件定义 + 总线配置
framework/
  __init__.py             → 公共API导出
  interfaces.py           → BaseComponent ABC
  bus.py                  → MessageBus：发布/订阅路由，通道管理
  config_loader.py        → JSON → ComponentRegistry + 总线配置
  registry.py             → ComponentRegistry：动态实例化
  pool.py                 → ObjectPool：组件实例重用
  cache.py                → ParamCache：参数哈希缓存
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
      "subscribes": ["data.loaded"]
    }
  ],
  "bus": {
    "default_channel": "highspeed"
  }
}
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

继承 `BaseComponent`，实现 `handle_message(message: Message) -> Any`：

```python
from framework.interfaces import BaseComponent
from framework.channels.base import Message

class MyComponent(BaseComponent):
    name: str = "my_component"

    def __init__(self, **params):
        super().__init__(**params)
        self.my_param = params.get("my_param", "default")

    def on_start(self):
        # 订阅主题
        if self._bus:
            self._bus.subscribe("my.topic", self.handle_message)

    def handle_message(self, message: Message):
        # 处理消息
        data = message.payload
        # 处理逻辑...
        return {"result": processed_data}
```

### 生命周期钩子

- `on_start()` - 组件启动，订阅主题
- `on_stop()` - 组件停止，清理资源
- `attach_bus(bus)` - 框架调用，连接总线
- `detach_bus()` - 框架调用，断开总线

### 发布消息

```python
self._bus.publish("topic.name", payload={"key": "value"}, sender=self.name)
```

## 性能特性

### 对象池 (ObjectPool)

- 组件实例重用，避免创建/销毁开销
- 工厂模式，可配置最大大小
- `acquire()` / `release()` 接口

### 参数缓存 (ParamCache)

- SHA256参数哈希键
- TTL过期，LRU驱逐
- 适用于确定性计算结果缓存

### 状态快照 (SnapshotManager)

- 捕获组件状态 + 待处理消息 + 缓存
- 中断恢复支持
- JSON磁盘持久化

## 通信模式

### 线程模式 (默认)

- 使用 `ThreadPoolExecutor` 线程池
- 适用于I/O密集型处理器

### 进程模式

- 使用 `multiprocessing.Pool`
- 每个处理器调用重新实例化组件
- 提供真正隔离和CPU安全性

### 异步模式

- 使用共享事件循环
- 协程处理器直接等待
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
- **进程模式**: `subscribe()` 需要 `handler_info` 用于子进程组件重建
- **组件验证**: `registry.create()` 通过importlib实例化，确保类路径正确且 `__init__` 参数可序列化

## 许可证

MIT License</content>
<filePath">D:\code-project\python\mfk\README.md
