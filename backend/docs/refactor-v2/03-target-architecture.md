# 03 — 目标架构

## 目标

将当前“RunService + TaskRunner + jobs.py + engine services”的耦合链路拆成四层：

1. API / Service layer
2. Run scheduler layer
3. Execution backend layer
4. Engine adapter layer

## 目标数据流

```text
POST /runs
  -> RunService
    -> RunRepository.create(run)
    -> RunScheduler.enqueue(run_id)

RunScheduler worker
  -> load run + workflow + project
  -> choose EngineAdapter
  -> ExecutionBackend.submit(adapter, execution_request)
  -> receive EngineEvent stream
  -> apply run state transitions
  -> publish SSE
```

## 模块边界

### 1. API layer

职责：

- 请求校验
- HTTP 错误映射
- response envelope

不负责：

- 执行引擎判断
- 调度逻辑

### 2. `RunService`

职责：

- 验证 workflow 与 project
- 校验 workspace 和输入
- 生成 run 记录
- 归档 request 数据
- 调用 scheduler enqueue/cancel
- 提供 logs/dag/outputs 等查询接口

不负责：

- 构建 Nextflow / WDL 命令
- 解析引擎 stdout/stderr
- 调度重试和 worker 生命周期

### 3. `RunScheduler`

职责：

- 持久化任务队列
- 优先级和并发控制
- 启动恢复
- 自动重试
- timeout / cleanup / hooks 的协调

不负责：

- 引擎细节

### 4. `ExecutionBackend`

职责：

- 进程启动
- stdout/stderr drain
- 取消进程
- 本地资源范围内的执行 lifecycle

首个实现只需要 `LocalBackend`。

### 5. `EngineAdapter`

职责：

- 生成命令
- 解析输出为统一事件
- 暴露 resume/cancel/schema 能力

预计实现：

- `NextflowAdapter`
- `WDLAdapter`

## 建议目录

```text
backend/app/
  engine/
    __init__.py
    backend.py
    adapter.py
    local.py
    registry.py
    adapters/
      nextflow.py
      wdl.py
  scheduler/
    __init__.py
    config.py
    models.py
    queue.py
    scheduler.py
    retry.py
    timeout.py
    cleanup.py
    hooks.py
    resources.py
    monitor.py
  runtime/
    events.py
    background_tasks.py
```

说明：

- `runtime/background_tasks.py` 用于承接 image pull 等非 run 后台任务
- run 的调度不再放在 `runtime/task_runner.py`

## 统一事件模型

建议所有引擎统一输出：

```python
class EngineEventType(str, Enum):
    PROCESS_INFO = "process"
    STARTED = "started"
    TASK_UPDATE = "task"
    LOG = "log"
    ERROR = "error"
    COMPLETED = "completed"
```

关键要求：

1. API/SSE 层不必知道原始引擎日志格式
2. scheduler 和 run event handler 只消费统一事件
3. 原始日志可以保留在 `data["raw"]`

## 调度模型

建议引入 `scheduled_tasks` 表，仅用于 run 调度。

### 状态

```text
queued -> dispatched -> completed
                   \-> failed
                   \-> cancelled
```

### 与 Run.status 的关系

- `scheduled_tasks.state` 是调度状态
- `runs.status` 是用户可见运行状态

两者不能混为一谈，但必须通过受控转换保持一致。

## Run 数据模型策略

### 原则

短期不做“激进拆表”，但要停止无序增长。

### 建议

1. 继续保留 `runs.config`
2. 加 `config_schema_version`
3. 使用 access helper
4. DAG 暂时仍可存放于 `config.ui.dag`
5. 运行时路径、pid、resume token 放到 `config.runtime`
6. retry/timeout 放到 `config.policy`

### 不建议在 V2 早期做的事情

1. 单独建立 DAG 表
2. 单独建立 runtime state 表
3. 彻底移除旧 key

这些动作会明显拉长迁移周期，且当前收益不足。

## API 保持兼容的原则

### 保持不变

- `/runs`
- `/runs/{id}`
- `/runs/{id}/logs`
- `/runs/{id}/dag`
- `/runs/{id}/outputs`
- `/runs/{id}/cancel`
- `/runs/{id}/resume`
- `/runs/{id}/retry`

### 新增但不破坏现有前端

- `/scheduler/status`
- `/scheduler/resources`
- `/runs/{id}/cleanup`
- `/runs/batch`

## 关于 WDL resume 的架构定位

V2 建议不要把它建模成和 Nextflow 完全相同的 resume token 语义。

更实际的做法是：

1. API 继续使用统一的 `/resume`
2. adapter 自己声明 `supports_native_resume` 与 `supports_best_effort_resume`
3. 对 WDL，run event handler 或 scheduler 只承诺“尝试复用 work dir 与已知完成信息”

## 关于 DAG 的架构定位

建议将 DAG 分成两层来源：

1. schema DAG
   来自 workflow schema / inspect / parser
2. runtime DAG
   来自运行事件和 trace

最终展示层可以合并这两层，但文档和代码中必须区分来源，避免把所有信息都塞进同一个脆弱匹配链。
