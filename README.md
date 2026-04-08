# 简单微框架示例

这个示例展示了一个极简的微框架：

- 使用 `framework/interfaces.py` 定义接口（`IPrinter`, `IFileReader`）。
- 使用 `config.json` 指定接口到实现的映射（按字符串路径）。
- `framework/config_loader.py` 根据配置动态导入并注册实现到 `ServiceRegistry`。
- `features/file_reader.py` 通过 `ServiceRegistry` 获取 `IPrinter`，并在不依赖具体实现的情况下调用它。


运行示例：

```bash
python main.py
```

配置说明：
- `config.json` 的 `pipeline` 字段定义按序执行的组件列表。
- 每个组件通过 `class` 指定模块路径，通过 `params` 传入构造参数。
- 组件通过继承 `framework.interfaces.BaseComponent` 并实现 `execute(context)`，在共享的 `context`（字典）中读写数据，或通过返回值进行链式传递（框架将最新返回值放到 `context['_last']`）。
- 顶层 `execution` 字段支持执行选项：`mode` = `serial` 或 `parallel`，`on_error` = `stop` 或 `continue`。

- 扩展选项：`execution.timeout` (秒)，`execution.retries`，`execution.max_workers`。
- 支持 `grouped` 模式：组件可在 `params` 中设置 `group` 字段，框架按出现顺序对组串行执行，组内并发执行。


超时与取消说明：
- 框架支持 `execution.timeout` 与 `params.timeout`（组件优先）作为秒级超时阈值，框架会用 `Future.result(timeout=...)` 等待执行。
- 在超时情况下框架会尝试 `Future.cancel()`，但对于线程池中的线程，Python 无法强制终止正在运行的线程——超时仅用于检测与控制流程（比如选择 `on_error` 策略），不能保证立即回收线程资源。

性能建议：长时间运行或需要可中断的任务应改为子进程（`ProcessPoolExecutor`）或协程（`asyncio`），以获得更好的超时/取消能力。

新后端说明：
- `execution.backend`: 支持 `thread`（默认）、`process`、`asyncio`。
- `process` 后端：框架为每次尝试创建一个独立子进程来执行组件（通过类路径与参数重新实例化），在超时时会 `terminate()` 子进程，从而实现更可靠的强制终止。
- `asyncio` 后端：在协程事件循环中并发运行组件；同步组件将被包装为线程执行（可用 `execute` 定义为 `async def` 提升效率）。

配置示例：
```
"execution": { "backend": "process", "mode": "grouped", "max_workers": 4, "timeout": 5, "retries": 2 }
```

这样框架仅负责配置解析与调度，功能模块通过继承抽象类实现具体逻辑。 
