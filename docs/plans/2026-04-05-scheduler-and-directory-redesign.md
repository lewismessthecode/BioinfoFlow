# 调度器与目录架构重设计

**日期**: 2026-04-05
**状态**: 讨论阶段，未开始实现
**触发**: ecoli-qc demo 因资源检查卡在排队，暴露了调度器和目录设计的多个问题

---

## 第一部分：调度器重设计

### 当前实现

调度器 (`backend/app/scheduler/`) 由以下组件构成：

| 模块 | 文件 | 职责 |
|------|------|------|
| Scheduler | `scheduler.py` | 主循环：启动 N 个 worker，从队列领取 task，检查资源，执行 run |
| TaskQueue | `queue.py` | 优先级队列，支持 delay_until、re-enqueue |
| ResourceMonitor | `monitor.py` | 每 30 秒采样系统资源（psutil: CPU/内存/磁盘/GPU） |
| ResourceEstimator | `resources.py` | 根据 workflow 名称猜测资源需求（small/medium/large 模板） |
| ResourceChecker | `resources.py` | 对比 available - safety_margin vs required，决定是否放行 |
| RetryEvaluator | `retry.py` | 指数退避重试策略 |
| TimeoutWatcher | `timeout.py` | 超时检测 |
| CleanupPolicy | `cleanup.py` | 完成后清理 |
| RunCompletionHooks | `hooks.py` | 审计、通知、批量更新 |

**当前执行链路：**

```
run 提交 → TaskQueue.enqueue()
         → worker claim_next()
         → _execute_task()
           → _wait_for_resources()     ← 问题在这里
             → ResourceEstimator.estimate()  → 猜测 "small" 模板
             → ResourceMonitor.current()     → psutil 采样
             → ResourceChecker.shortage_reasons()
               → required.cpu (1) > available.cpu (3.78) - safety.cpu (2)?
               → 如果是 → re-enqueue（延迟 30 秒），run 继续排队
               → 如果否 → _execute_run_id()
```

**关键配置（`config.py` 第 93-102 行）：**

```python
scheduler_max_concurrency: int = 4           # 并发 worker 数
scheduler_resource_check_enabled: bool = True # 资源检查默认开启
scheduler_safety_cpu: int = 2                 # CPU 安全余量
scheduler_safety_memory_gb: float = 2.0       # 内存安全余量
scheduler_safety_disk_gb: float = 10.0        # 磁盘安全余量
```

**资源模板（`resources.py` 第 30-52 行）：**

```python
RESOURCE_TEMPLATES = {
    "small":  ResourceRequirements(cpu=1, memory_gb=2.0,  disk_gb=5.0),
    "medium": ResourceRequirements(cpu=2, memory_gb=4.0,  disk_gb=10.0),
    "large":  ResourceRequirements(cpu=3, memory_gb=6.0,  disk_gb=20.0),
    "xlarge": ResourceRequirements(cpu=4, memory_gb=8.0,  disk_gb=30.0),
    "gpu":    ResourceRequirements(cpu=2, memory_gb=8.0,  disk_gb=20.0, gpu=1),
}
```

**Pipeline 名称映射（`resources.py` 第 83-91 行）：**

```python
PIPELINE_TEMPLATES = {
    "viralrecon": "small", "rnaseq": "small", "sarek": "medium",
    "fetchngs": "small",  "ampliseq": "small", "taxprofiler": "small",
    "mag": "small",
}
# 未匹配的 workflow → 默认 "small"
```

### 当前问题

**1. 资源估算是在猜，而且猜得不准**

ecoli-qc 只用一个 `python:alpine` 容器数几行 FASTQ，实际消耗 < 0.5 CPU + 100MB 内存。但因为不在 `PIPELINE_TEMPLATES` 中，默认被分配 "small"（1 CPU, 2GB）。加上 safety margin（2 CPU, 2GB），实际门槛变成了 3 CPU + 4GB 空闲才能执行。在 MacBook（8 核，load avg ~4）上经常被卡住。

**2. Nextflow/WDL 自身已经管理了 task 级资源**

Nextflow 的 `process { cpus; memory }` 和 WDL 的 `runtime {}` 在 task 粒度做资源分配。调度器去估算 pipeline 级资源是**越界行为** — 它不知道 pipeline 内部有多少 task、每个 task 要多少资源。

**3. 固定 max_concurrency 不够灵活**

`max_concurrency=4` 假设所有 run 消耗相同资源。但现实中：
- ecoli-qc：2 秒完成，几乎不消耗资源
- WGS pipeline：跑几小时，吃满所有核心
- 用户可能一次投 100+ 个轻量 run

**4. 资源检查对开发环境过于保守**

safety margin 是固定值（2 CPU, 2GB 内存, 10GB 磁盘），在 8 核 MacBook 上 CPU 余量占了 25%。load avg 稍微波动就会阻塞所有 run。

### 业界参考

| 平台 | 调度策略 | 资源管理 |
|------|---------|---------|
| **Nextflow Tower** | 并发控制 + pipeline 级 slots | 委托给 executor（local/slurm/k8s） |
| **Cromwell** | 队列 + 重试 | 委托给 backend（JES/HPC） |
| **Galaxy** | job slots（固定并发数） | 每个 tool 自己声明 |
| **Airflow** | worker pool + parallelism | 不管 task 内部资源 |

共同点：**调度器控制准入（admission control），不在 pipeline 级做资源估算。**

### 新设计：Slots 模型

**核心思想：每个 run 有一个 weight，调度器维护一个 slots 池，weight 之和不超过 total_slots。**

```
┌─ Slots 池: 8 (默认 = CPU 核数) ───────────────────┐
│                                                     │
│  WGS pipeline:  weight=4  → 占 4/8 slots           │
│  ecoli-qc #1:   weight=1  → 占 5/8 slots           │
│  ecoli-qc #2:   weight=1  → 占 6/8 slots           │
│  ecoli-qc #3:   weight=1  → 占 7/8 slots           │
│  ecoli-qc #4:   weight=1  → 占 8/8 slots           │
│  rnaseq:        weight=2  → 排队（剩余 0 < 2）      │
│                                                     │
│  ecoli-qc #1 完成 → 释放 1 slot → 剩余 1           │
│  ecoli-qc #2 完成 → 释放 1 slot → 剩余 2 ≥ 2      │
│  rnaseq 放行                                        │
└─────────────────────────────────────────────────────┘
```

**配置简化：**

```python
# 新配置（替代当前的 max_concurrency + resource_check_* 系列）
scheduler_total_slots: int = 0           # 0 = 自动检测（CPU 核数）
scheduler_max_processes: int = 0         # 0 = 不限制进程数（由 slots 控制）
scheduler_default_weight: int = 1        # workflow 未声明 weight 时的默认值
```

**weight 来源：**

1. Workflow 注册时声明（最优先）— 对应 `DemoSpec.scale` 的映射
2. 用户在 UI 上调整（可选）
3. 默认 = 1（未声明时，最轻量）

**scale → weight 映射：**

```python
SCALE_WEIGHTS = {
    "small": 1,     # ecoli-qc, coronavirus
    "medium": 2,    # deaf-20, sarek
    "large": 4,     # parabricks-wgs
    "xlarge": 6,
}
```

**关键区别：**
- 没声明 weight → 默认 1 → 几乎不受限（对比当前：没声明 → 猜 "small" → 被 safety margin 卡住）
- 不需要 psutil、不需要 ResourceMonitor、不需要 safety margin
- 并发数自然由 slots 控制（8 slots 池最多 8 个 weight=1 的 run，或 2 个 weight=4 的 run）

### 要移除的模块

| 模块 | 文件 | 原因 |
|------|------|------|
| ResourceMonitor | `monitor.py` | 不再需要实时系统资源采样 |
| ResourceEstimator | `resources.py` | 不再猜测 pipeline 资源需求 |
| ResourceChecker | `resources.py` | 由 slots 模型替代 |
| SafetyMargin | `resources.py` | 不再需要 |
| RESOURCE_TEMPLATES | `resources.py` | 由 workflow.weight 替代 |
| PIPELINE_TEMPLATES | `resources.py` | 由 workflow.weight 替代 |

**保留的模块不变：** TaskQueue, RetryEvaluator, TimeoutWatcher, CleanupPolicy, RunCompletionHooks。

### 需要修改的文件

| 文件 | 变更 |
|------|------|
| `scheduler/scheduler.py` | `_wait_for_resources()` → `_wait_for_slots()`，用 slots 计数替代资源检查 |
| `scheduler/config.py` | 替换 `resource_check_*` 系列为 `total_slots`, `default_weight` |
| `scheduler/resources.py` | 大幅简化，只保留 weight 映射 |
| `scheduler/monitor.py` | 可选保留用于 `/scheduler/resources` API 展示，但不再阻塞调度 |
| `config.py` | 替换 `scheduler_safety_*` 系列 |
| `models/workflow.py` | 新增 `weight` 字段（int, 默认 1） |
| `services/demo_catalog.py` | `DemoSpec.scale` → `DemoSpec.weight`（或自动映射） |
| `api/v1/scheduler.py` | `/scheduler/status` 返回 slots 使用情况 |

### 可选增强：系统红线保护

作为 slots 模型的补充，可以保留一个极简的系统保护（不阻塞正常调度，只在极端情况暂停）：

```python
# 红线检查（可选，默认关）
scheduler_system_guard_enabled: bool = False
scheduler_min_memory_gb: float = 1.0    # 可用内存低于此值时暂停所有调度
scheduler_min_disk_gb: float = 2.0      # 可用磁盘低于此值时暂停所有调度
```

这不是准入检查，而是**熔断器** — 系统快崩溃时暂停一切，恢复后自动继续。

---

## 第二部分：目录架构重设计

### 当前实现

**项目 workspace 模型（`models/project.py`）：**

```python
workspace_path: str       # 项目根目录（绝对或相对路径）
data_roots: list | None   # 额外数据挂载点（JSON，新增于 migration 0011）
```

**路径解析（`utils/paths.py`）：**
- 相对路径 → 相对于 `repo_root()`（代码仓库根目录）
- 绝对路径 → 直接使用
- `safe_workspace()` 防止路径遍历攻击

**当前运行时目录布局：**

```
<project_workspace>/
├── <input_files>                          # 用户数据（和其他文件混在一起）
├── results/                               # 所有 run 共享一个 results 目录！
├── .bioinfoflow/
│   └── <run_id>/
│       ├── inputs/samplesheet.csv         # 物化的输入
│       ├── refs/reference.fasta           # 物化的参考
│       ├── dag.dot                        # DAG 可视化
│       ├── trace.tsv                      # 执行追踪
│       └── run.manifest.json              # 提交快照
├── .nextflow/                             # Nextflow 缓存
└── .bioinfoflow_overrides_run_*.config    # Nextflow 配置覆盖

Engine 中间文件在外部：
/tmp/bioinfoflow/work/<run_id>/            # Nextflow work dir
/tmp/bioinfoflow/miniwdl/<run_id>/         # WDL work dir
```

**Demo 数据（`demo/` 在 repo 根目录）：**

```
demo/
├── ecoli-qc/         # workspace_path="demo/ecoli-qc", scale="small"
│   ├── main.nf
│   ├── reads/        # 内置测试数据
│   └── ref/
├── coronavirus-surveillance/   # scale="small"
├── parabricks-wgs/             # scale="large"
└── deaf-20/                    # scale="medium"
```

### 当前问题

**1. Run 输出不隔离**

所有 run 的 `--outdir` 默认都是 `results/`。在同一个 workspace 下多次运行，后跑的会覆盖先跑的输出。无法比较不同 run 的结果，无法干净地删除单次 run 的输出。

**2. `.bioinfoflow/` 职责混乱**

混合了平台元数据（manifest.json）和 engine 产物（dag.dot, trace.tsv）。`.bioinfoflow_overrides_*.config` 散落在 workspace 根目录。

**3. Demo 数据耦合代码仓库**

`demo/` 在 repo 根目录，Docker 部署时需要额外处理。不应该让运行时依赖代码目录结构。

**4. 共享参考数据无解**

参考基因组（hg38, 3-50GB）、注释数据库（dbSNP, VEP, 1-100GB）跨 workflow 共享，但当前没有全局引用机制。每个项目各自管理，导致冗余和路径混乱。

**5. Workspace 概念过载**

`workspace` 同时是项目根目录、Nextflow 启动目录（cwd）、输入数据所在地、输出存放地。

### 数据分类与生命周期

| 数据类别 | 大小 | 生命周期 | 共享范围 | 谁写 | 谁读 |
|---------|------|---------|---------|------|------|
| **参考基因组** | 3-50 GB | 几乎永久 | 全局（跨项目跨 workflow） | 管理员 | Engine |
| **注释数据库** | 1-100 GB | 按版本更新 | 全局 | 管理员 | Engine |
| **Index/缓存** | 1-30 GB | 跟随参考基因组 | 全局 | Engine/管理员 | Engine |
| **Panel/BED** | < 1 MB | 按项目变化 | 项目内 | 用户 | Engine |
| **样本数据** (FASTQ) | 1-100 GB | 按项目 | 项目内 | 用户/测序仪 | Engine |
| **Samplesheet** | < 1 MB | 按 run | 单次 run | 平台 | Engine |
| **Run 输出** | 可变 | 按 run 保留 | 单次 run | Engine | 用户 |
| **Engine 中间文件** | 大 | 临时 | 单次 run | Engine | Engine |
| **平台元数据** | < 1 MB | 跟随 run | 单次 run | 平台 | 平台/UI |

### 新设计

#### 全局共享资源：Reference Stores

**设计思路：** 参考基因组、数据库等大文件全局一份，所有项目通过逻辑名引用。类似 Docker image registry — 数据在一个地方，所有容器共享。

```yaml
# 平台级配置（config.py 或 /etc/bioinfoflow/config.yaml）
reference_stores:
  - name: "genomes"
    path: "/mnt/references/genomes"      # 或本地 ~/references/genomes
  - name: "databases"
    path: "/mnt/references/databases"
  - name: "indices"
    path: "/mnt/references/indices"
```

**数据按物种/版本/类型组织（不按 workflow 组织）：**

```
/mnt/references/
├── genomes/
│   ├── hg38/
│   │   ├── hg38.fa
│   │   ├── hg38.fa.fai
│   │   └── hg38.dict
│   ├── GRCm39/
│   └── NC_000913.3/                  # E. coli
├── databases/
│   ├── dbsnp/v156/
│   ├── vep/112/
│   └── kraken2/standard-16gb/
└── indices/
    ├── bwa-mem2/hg38/
    └── star/hg38-gencode-v44/
```

**Workflow 引用方式：**

```json
{
  "reference": "@genomes/hg38/hg38.fa",
  "dbsnp": "@databases/dbsnp/v156/dbsnp.vcf.gz",
  "reads": "data/reads/*_{R1,R2}.fastq.gz"
}
```

- `@` 前缀 → 从全局 reference_store 解析（只读）
- 普通相对路径 → 从项目 workspace 解析
- 绝对路径 → 必须在 data_roots 白名单内

前端 file browser 新增 Reference Stores tab，和 data_roots tab 并列显示。

#### 项目目录结构

```
<project_root>/                     # Project.workspace_path
│
├── data/                           # 项目输入数据（用户管理，长期保留）
│   ├── reads/
│   │   ├── sample1_R1.fastq.gz
│   │   └── sample1_R2.fastq.gz
│   └── samplesheets/
│       └── batch-42.csv
│
├── runs/                           # Run 输出 + 元数据（平台管理，按 run_id 隔离）
│   ├── run_2824e4/
│   │   ├── results/                # --outdir 自动指向这里
│   │   │   ├── reads/
│   │   │   ├── reference/
│   │   │   └── summary_report.txt
│   │   ├── manifest.json           # 提交快照（谁、何时、什么参数）
│   │   ├── inputs/                 # 物化的输入（samplesheet 快照等）
│   │   ├── dag.dot
│   │   ├── trace.tsv
│   │   └── logs/
│   └── run_883a88/
│       └── ...
│
├── .bioinfoflow/                   # 平台级项目配置（不含 run 数据）
│   └── config.json                 # 项目配置缓存
│
└── .work/                          # Engine 中间文件（可随时安全清理）
    └── <nextflow session hash>/
```

**设计决策说明：**

1. **`runs/<run_id>/` 合并元数据和输出结果** — 不拆分。用户查看 run 时需要结果 + DAG + trace + 参数，它们是一体的。删除 run 时一个目录全清。归档 run 时打包一个目录即可。

2. **`data/` 是约定目录** — 不强制。用户可以把 FASTQ 放在任意位置（通过 file browser 选择），`data/` 只是推荐的组织方式。

3. **`.bioinfoflow/` 只放项目配置** — 不再放 run 数据。run 数据统一在 `runs/` 下。

4. **`.work/` 替代 `/tmp/bioinfoflow/work/`** — 把 engine 中间文件放在项目内（可配置），方便 Nextflow `-resume` 使用缓存。放在 `/tmp` 下重启后缓存丢失，无法 resume。

#### Demo 数据

当前 `demo/` 在 repo 根目录。改为：

**开发环境：** `demo/` 保留在 repo 中作为测试资源。
**生产/Docker 部署：** 打包到 image 或 volume mount。

```yaml
# docker-compose.yaml
volumes:
  - bundled-demos:/app/bundled:ro

# 或 Dockerfile
COPY demo/ /app/bundled/
```

`DemoService.seed()` 从可配置路径读取：

```python
# config.py
bundled_demos_path: str = "demo"  # 开发时用 repo 内路径
                                   # 部署时设为 /app/bundled
```

Demo 创建项目时自动设置正确的 workspace。不再需要用户手动填 `demo/ecoli-qc` 作为工作区。

### 路径关系总览

```
┌─────────────────────────────────────────────────────────┐
│ 平台全局                                                │
│   reference_stores:                                      │
│     @genomes  → /mnt/references/genomes     (只读)       │
│     @databases → /mnt/references/databases  (只读)       │
├─────────────────────────────────────────────────────────┤
│ 项目级                                                   │
│   project.workspace_path → <project_root>               │
│   project.data_roots → ["/mnt/nas/seq/batch-42"]  (只读) │
│                                                          │
│   <project_root>/data/*         ← 项目内数据 (读写)      │
│   <project_root>/runs/<run_id>/ ← 运行输出+元数据        │
│   <project_root>/.bioinfoflow/  ← 项目配置               │
│   <project_root>/.work/         ← Engine 临时文件        │
├─────────────────────────────────────────────────────────┤
│ 安全边界                                                 │
│   safe_workspace()     → 防止路径遍历出 project_root     │
│   data_roots           → 显式白名单，只读浏览             │
│   reference_stores     → 显式白名单，只读浏览             │
│   @ 前缀解析           → 只从 reference_stores 解析       │
└─────────────────────────────────────────────────────────┘
```

---

## 需要修改的模块汇总

### 调度器部分

| 文件 | 当前行数 | 变更类型 | 说明 |
|------|---------|---------|------|
| `scheduler/scheduler.py` | ~600 | 重构 | `_wait_for_resources` → `_wait_for_slots` |
| `scheduler/config.py` | ~20 | 简化 | 移除 `resource_check_*`，新增 `total_slots`, `default_weight` |
| `scheduler/resources.py` | ~160 | 大幅简化 | 移除 Templates/Estimator/Checker，保留 weight 映射 |
| `scheduler/monitor.py` | ~100 | 可选保留 | 降级为 API 展示用，不阻塞调度 |
| `config.py` | 第 93-102 行 | 替换 | 新 scheduler 配置项 |
| `models/workflow.py` | — | 新增字段 | `weight: int = 1` |
| `services/demo_catalog.py` | — | 映射 | `scale` → `weight` |
| `api/v1/scheduler.py` | — | 更新 | 返回 slots 使用信息 |

### 目录架构部分

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `scheduler/scheduler.py` 第 437-475 行 | 重构 | workspace 解析 + outdir 自动指向 `runs/<run_id>/results` |
| `services/run_submission_service.py` | 重构 | 归档目录从 `.bioinfoflow/<run_id>` 改到 `runs/<run_id>` |
| `services/run_helpers.py` | 更新 | `safe_workspace()` 支持 reference_stores 路径解析 |
| `services/file_service.py` | 扩展 | 新增 reference_stores 浏览支持 |
| `services/demo_service.py` | 重构 | 可配置 bundled path，自动设置 workspace |
| `services/demo_catalog.py` | 更新 | 移除 `workspace_path`，改为 bundled path 推导 |
| `utils/paths.py` | 扩展 | 新增 `resolve_reference()` 处理 `@` 前缀 |
| `config.py` | 新增 | `reference_stores`, `bundled_demos_path` |
| `api/v1/files.py` | 扩展 | 新增 reference_stores 参数 |
| `frontend/file-browser-dialog.tsx` | 扩展 | 新增 Reference Stores tab |
| `alembic/` | 新 migration | workflow 表新增 weight 字段 |

---

## 实施建议

建议分三个阶段：

**Phase 1（解除当前阻塞）：**
- 关闭资源检查默认值（`scheduler_resource_check_enabled=False`）
- Run outdir 自动改写为 `runs/<run_id>/results`
- Demo 提交时自动填充正确的 workspace

**Phase 2（Slots 模型）：**
- 实现 slots 准入控制替代 resource check
- Workflow 模型新增 weight 字段
- 移除 ResourceEstimator, RESOURCE_TEMPLATES, PIPELINE_TEMPLATES

**Phase 3（Reference Stores + 目录整理）：**
- 实现全局 reference_stores 配置
- `@` 前缀路径解析
- 前端 file browser 支持 reference stores tab
- Demo 数据可配置路径
