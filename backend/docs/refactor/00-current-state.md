# 00 — 当前实现总结、局限与痛点

## 一、架构总览

### 数据流

```
用户请求 → API (runs.py)
  → RunService (验证 + 预检 + 归档)
    → TaskRunner.submit() (内存FIFO队列, 固定2并发)
      → execute_run() (后台Job, 新建独立DB session)
        → NextflowService / MiniWDLService (子进程 asyncio.create_subprocess_exec)
          → stdout/stderr 异步流读取 → _handle_run_event() 事件分发
            → EventBus.publish() → SSE → 前端实时更新
```

### 核心文件

| 层级 | 文件 | 行数 | 职责 |
|------|------|------|------|
| API | `api/v1/runs.py` | 322 | REST端点: list/create/cancel/resume/retry/delete + logs/dag/outputs |
| 业务 | `services/run_service.py` | 1071 | 运行生命周期、参数验证、路径安全、归档 |
| 调度 | `runtime/task_runner.py` | 62 | asyncio Queue + Worker Pool (硬编码并发=2) |
| 执行 | `runtime/jobs.py` | 563 | execute_run: 引擎调用 + DAG/日志/状态更新 |
| 引擎 | `services/nextflow_service.py` | 256 | Nextflow子进程: 命令构建 + stdout解析 + cancel |
| 引擎 | `services/miniwdl_service.py` | 189 | MiniWDL子进程: 命令构建 + 输出拷贝 + cancel |
| 事件 | `runtime/events.py` | 257 | EventBus: 内存pub/sub + SSE推送 |
| 模型 | `models/run.py` | 49 | Run ORM: 状态、config JSON、进度字段 |
| 验证 | `services/workflow_validator.py` | 546 | WDL/Nextflow 语法解析 + schema提取 |
| DAG | `utils/dag_builder.py` | 191 | schema → React Flow DAG可视化 |

### 运行状态机

```
PENDING → QUEUED → RUNNING → COMPLETED
                          ↘ FAILED → (resume/retry → 新Run PENDING)
                          ↘ CANCELLED
```

### 存储结构

```
{workspace}/.bioinfoflow/{run_id}/
├── run.manifest.json          # 元数据快照
├── inputs/
│   ├── params.json            # 参数
│   ├── inputs.json            # WDL inputs
│   ├── config_overrides.json  # 引擎配置覆盖
│   └── samplesheet.csv        # (wizard模式)
├── refs/
│   └── reference.fasta        # (如适用)
├── run.log                    # 执行日志
├── dag.dot                    # Nextflow DAG
├── trace.tsv                  # Nextflow trace
└── miniwdl/                   # (WDL工作目录)
```

---

## 二、做得好的部分

### 1. 安全的路径验证
`run_service.py:968-972` — `_safe_workspace()` 使用 `Path.resolve()` + `is_relative_to()` 防止目录遍历，在所有路径操作前调用。

### 2. 运行归档保证可复现性
`run_service.py:63-99` — `_persist_run_archive()` 在运行创建时快照所有参数，包含 secret 自动脱敏 (`_redact_secrets`)。

### 3. SSE实时事件推送
`runtime/events.py` — 内存 pub/sub + 队列满时丢弃旧事件策略，保证实时性。支持 project/conversation/run 级别过滤。

### 4. 参数自动推断
`RunProfileService` 根据 workflow 名称和 workspace 内容自动发现 samplesheet/reads/reference 路径。

### 5. 统一的API响应格式
`{ success, data, error, meta }` envelope 模式，一致的错误码和HTTP状态码映射。

### 6. 双引擎支持
Nextflow + WDL 两条执行路径，覆盖主流生信工作流定义。

---

## 三、核心局限与痛点

### 痛点1: TaskRunner — 最小化的调度器

**位置**: `runtime/task_runner.py` (仅62行)

```python
class TaskRunner:
    def __init__(self, max_concurrency: int = 2) -> None:
        self.queue: asyncio.Queue | None = None
        self.max_concurrency = max_concurrency  # 硬编码为2
```

**问题清单**:

| 问题 | 影响 | 严重性 |
|------|------|--------|
| 固定2并发 | 100个任务只有2个在跑 | 高 |
| 内存FIFO队列 | 服务重启丢失所有排队任务 | 高 |
| 无优先级 | 紧急任务无法插队 | 中 |
| 无背压 | 无界队列，理论上可以无限排队 | 中 |
| 无资源检查 | 不知道机器是否有足够资源 | 高 |
| 同进程执行 | 一个任务异常可能影响worker | 中 |
| 无任务追踪 | 无法查询队列中的任务状态 | 中 |

### 痛点2: execute_run — 巨型单体函数

**位置**: `runtime/jobs.py:111-305` (~195行单函数)

问题:
- `execute_run()` 是一个巨大的 async 函数，混合了: DB操作、引擎选择、配置构建、事件处理、错误恢复
- 引擎选择通过 `if/elif` 硬编码，新增引擎需要修改此函数
- Nextflow 和 WDL 的配置构建逻辑内联在函数中，无法复用
- Docker可用性检查和配置注入只在 Nextflow 分支中 (WDL忽略了Docker)

### 痛点3: 引擎服务无统一接口

**位置**: `services/nextflow_service.py`, `services/miniwdl_service.py`

- `NextflowService` 和 `MiniWDLService` 没有共同的基类或接口
- 事件格式不统一: Nextflow 发出 `started`/`task`/`completed` 等丰富事件; WDL 只有 `log`/`error`/`completed`
- Cancel机制不同: Nextflow支持pid+run_name两种; WDL只支持pid
- Resume: Nextflow有 (`-resume`); WDL完全不支持
- 命令构建: 各自独立实现 `_build_command()`

### 痛点4: WorkflowValidator 单文件正则解析

**位置**: `services/workflow_validator.py`

- Nextflow 验证完全基于正则 (无AST解析)
- 无法处理 DSL2 的 `include { PROCESS } from './modules/...'`
- 只解析主文件，忽略所有 import/include
- nf-core 和 github 来源的管线没有本地文件可解析 → `schema_json` 为空
- WDL 验证依赖 `import WDL` (miniwdl库)，如果未安装则回退到更弱的正则

### 痛点5: DAG 节点匹配脆弱

**位置**: `utils/dag_builder.py`, `runtime/jobs.py:406-456`

匹配链路:
```
运行时 stdout "process > nf-core/viralrecon:FASTQC (sample1)"
  → clean_process_label() → "FASTQC"
  → normalize_dag_id() → "fastqc"
  → 与 schema_json 中的节点ID比较
```

问题:
- 如果 schema 中用的是 `FASTQC_RAW` 而运行时输出 `FASTQC`，无法匹配
- `clean_process_label` 只处理了两种模式 (冒号前缀和括号后缀)，不处理其他变体
- 无模糊匹配、无别名映射

### 痛点6: 无断点续运 (WDL) 和 无自动重试

- Resume: `run_service.py:437-491` 只支持 Nextflow (`-resume` flag)
- WDL 的 `MiniWDLService` 没有任何 resume/checkpoint 机制
- `retry_run()` 是"从头重跑"，不是步骤级重试
- 无平台级自动重试 (OOM、网络中断等需要手动干预)

### 痛点7: 无运行超时

- `execute_run()` 可以无限运行，没有超时保护
- 生信管线可能因为bug而挂起 (如等待输入、死锁)
- 唯一的保护是 `recover_stale_runs()` (30分钟后标记stale)，但这只在服务重启时运行

### 痛点8: Work-dir 不清理

- Nextflow 的 `work_dir` (`/tmp/bioinfoflow/work/{run_id}`) 随运行累积
- MiniWDL 的 `{workspace}/.bioinfoflow/miniwdl/{run_id}` 同样累积
- 没有清理策略、没有磁盘空间检查
- 长期运行后磁盘空间耗尽

### 痛点9: Run.config JSON 过载

**位置**: `models/run.py:35`

`config` 字段承载了太多职责:
```python
config = {
    "params": {...},           # 用户参数
    "inputs": {...},           # WDL inputs
    "config_overrides": {...}, # 引擎配置
    "resolved_runspec": {...}, # 解析后的参数
    "runtime": {               # 运行时状态
        "pid": int,
        "engine": str,
        "session_id": str,
        "dag_path": str,
        "trace_path": str,
        "docker_available": bool,
    },
    "resume": bool,            # resume标记
    "resume_from": str,        # resume token
    "dag": {...},              # 完整DAG数据 (可能很大)
    "log_path": str,           # 日志路径
}
```

问题:
- 单个 JSON 字段存储了配置、状态、DAG数据、运行时信息
- DAG 数据可能很大 (几十个节点)，每次更新都需要序列化整个 config
- 没有类型约束，任何代码都可以往 config 里塞任意字段
- `flag_modified(run, "config")` 到处使用，容易遗忘

### 痛点10: 服务实例无复用

**位置**: `runtime/jobs.py`, `api/v1/runs.py`

每个请求和每次事件处理都创建新的服务实例:
```python
# jobs.py:115-116
from app.services.run_service import RunService
run_service = RunService(session)

# runs.py:39
service = RunService(db)
```

以及引擎服务:
```python
# jobs.py:236
service = NextflowService()  # 每次execute_run都新建
```

虽然这些是轻量级对象，但在高并发场景下是不必要的开销。

---

## 四、API 接口评估

### 当前端点

| 方法 | 路径 | 充分性 |
|------|------|--------|
| GET | `/runs` | ✅ 基本够用，缺少batch查询 |
| POST | `/runs` | ✅ 基本够用，缺少retry_policy/timeout |
| POST | `/runs/wizard` | ✅ 特化场景 |
| GET | `/runs/{id}` | ✅ 足够 |
| GET | `/runs/{id}/logs` | ✅ 足够 |
| GET | `/runs/{id}/dag` | ✅ 足够 |
| GET | `/runs/{id}/outputs` | ✅ 足够 |
| GET | `/runs/{id}/outputs/download` | ✅ 足够 |
| POST | `/runs/{id}/cancel` | ✅ 足够 |
| POST | `/runs/{id}/resume` | ⚠️ 仅NF，需扩展到WDL |
| POST | `/runs/{id}/retry` | ⚠️ 全量重跑，缺少自动重试 |
| DELETE | `/runs/{id}` | ✅ 足够 |

### 缺失的端点

| 需要 | 说明 |
|------|------|
| `POST /runs/batch` | 批量投递 |
| `GET /runs/batch/{id}` | 批次状态查询 |
| `POST /runs/batch/{id}/cancel` | 批量取消 |
| `POST /runs/{id}/cleanup` | 清理work-dir |
| `GET /scheduler/status` | 调度器状态 (队列深度、worker数) |
| `GET /scheduler/resources` | 当前资源使用情况 |

---

## 五、技术债务清单

1. `run_service.py` (1071行) 超出了 400 行推荐上限，应拆分
2. `execute_run()` (195行) 超出了 50 行函数上限
3. `run.config` JSON 字段缺乏类型约束
4. 引擎服务无共同接口，`jobs.py` 中的 if/elif 会随引擎增加膨胀
5. `task_runner.py` 硬编码 `max_concurrency=2`，不可配置
6. WorkflowValidator 的正则解析无法处理复杂管线
7. 无超时、无磁盘监控、无审计日志
