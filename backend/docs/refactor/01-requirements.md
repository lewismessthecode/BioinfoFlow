# 01 — 需求和场景完整梳理

## 决策前提

| 决策项 | 结论 | 理由 |
|--------|------|------|
| 引擎 | 双引擎: Nextflow (主) + WDL (辅) | 引擎抽象层本身就需要，边际成本低；覆盖更广用户群 |
| 部署 | 先 Local, 预留 SSH/Cloud 接口 | 降低初期复杂度，保持架构可扩展 |
| Cromwell | 不接入 | 保持 Python 单体架构简洁；WDL resume 通过应用层实现 |
| Scope 外 | Agent自动串流程, DAG drag-and-drop | 后续 worktree 实现 |

---

## 需求分类

### R1: 引擎抽象层 (优先级: P0 — 基础)

**目标**: 统一 Nextflow 和 WDL 的执行、取消、事件模型。

| 需求 | 描述 | 来源 |
|------|------|------|
| R1.1 | 定义 `ExecutionBackend` async interface (submit/cancel/status/logs) | 架构设计 |
| R1.2 | 实现 `LocalBackend` — 本地子进程执行 | 当前实现迁移 |
| R1.3 | 预留 `SSHBackend` / `CloudBackend` 接口 (仅定义，不实现) | 部署路径 |
| R1.4 | 定义 `EngineAdapter` interface (build_command/parse_events/get_resume_token) | 引擎差异抽象 |
| R1.5 | 重构 NextflowService → NextflowAdapter | 代码迁移 |
| R1.6 | 重构 MiniWDLService → WDLAdapter | 代码迁移 |
| R1.7 | 统一事件模型 `EngineEvent` dataclass | 消除引擎间事件差异 |
| R1.8 | 消除 `execute_run()` 中的 if/elif 引擎分支 | 技术债务 |

### R2: 调度器核心 (优先级: P0 — 基础)

**目标**: 替换 TaskRunner，实现持久化优先级调度。

| 需求 | 描述 | 来源 |
|------|------|------|
| R2.1 | 可配置并发数 (config: `scheduler_max_concurrency`) | 痛点1 |
| R2.2 | 持久化任务队列 — DB表 `scheduled_tasks` | 痛点1: 服务重启丢失 |
| R2.3 | 优先级排序 (urgent/normal/low) | 批量投递场景 |
| R2.4 | 队列背压 — 深度限制 + 拒绝策略 | 防止内存溢出 |
| R2.5 | 启动恢复 — QUEUED/RUNNING 任务自动重排或标记失败 | 痛点1 |
| R2.6 | 调度器状态查询 API (`GET /scheduler/status`) | 运维需求 |
| R2.7 | 与 ExecutionBackend 集成 | 架构依赖 |

### R3: 资源感知调度 (优先级: P1)

**目标**: 根据系统可用资源动态投递任务。

| 需求 | 描述 | 来源 |
|------|------|------|
| R3.1 | 资源探测 — CPU/Memory/Disk/GPU (psutil) | Layer 1 |
| R3.2 | 任务资源需求声明 — 从 workflow config 提取或使用默认模板 | Layer 2 |
| R3.3 | 投递前资源检查 — available >= required + safety_margin | Layer 3 |
| R3.4 | 系统安全阈值 — 保留 10% memory, 2 CPU, 10GB disk | Layer 4 |
| R3.5 | 磁盘空间预检 — 投递前检查 workspace 可用空间 | 痛点8 |
| R3.6 | 资源状态 API (`GET /scheduler/resources`) | 运维需求 |
| R3.7 | 定期资源采样 (configurable interval, default 30s) | 性能基线 |

### R4: 断点续运 + 自动重试 (优先级: P0)

**目标**: 全引擎 resume，平台级自动重试。

| 需求 | 描述 | 来源 |
|------|------|------|
| R4.1 | Nextflow resume 保持现有 `-resume` 逻辑 | 迁移 |
| R4.2 | WDL resume — 应用层 task 完成记录 + 重入跳过 | 新需求 |
| R4.3 | `RetryPolicy` — max_retries, delay, backoff, retry_on | 新需求 |
| R4.4 | RunCreate API 添加 `retry_policy` 字段 | API扩展 |
| R4.5 | 调度器自动重试 — 失败时检查 policy → 自动重新提交 | 平台级重试 |
| R4.6 | 重试计数器 + 历史记录 | 可观测性 |
| R4.7 | Nextflow 引擎级重试 — 注入 `process.errorStrategy` | 步骤级重试 |
| R4.8 | OOM 重试 — 检测 OOM 错误 + 自动增加资源 | 生信场景 |

**重试场景矩阵**:

| 场景 | 重试类型 | 触发条件 | 行为 |
|------|----------|----------|------|
| 网络下载中断 | 步骤级自动重试 | exit code + error pattern | 重试当前步骤 |
| OOM | 步骤级重试+增加资源 | OOM error pattern | 增加 memory → 重试 |
| 临时文件系统满 | 步骤级延迟重试 | disk error pattern | 等待 → 重试 |
| 整个管线失败 | 断点续运 | 用户触发 / 自动 | resume from checkpoint |
| 参数错误 | 不重试 | validation error | 通知用户 |

### R5: DAG 兼容性 (优先级: P1)

**目标**: 提升新注册流程的 DAG 解析和运行时兼容。

| 需求 | 描述 | 来源 |
|------|------|------|
| R5.1 | Nextflow: 利用 `nextflow inspect` 获取管线结构 | 替代正则 |
| R5.2 | nf-core: 调用 `nf-core schema` 获取标准 schema | 提升覆盖率 |
| R5.3 | WDL: 利用 `miniwdl check` 获取 task/dependency 信息 | 替代正则 |
| R5.4 | 运行时 DAG — 以实际执行为准 (trace file 动态构建) | 覆盖无schema场景 |
| R5.5 | 节点匹配优化 — 模糊匹配 + 前缀剥离 + 别名映射 | 痛点5 |
| R5.6 | schema_json 标准化格式 + 版本迁移 | 数据一致性 |
| R5.7 | WorkflowValidator 重构 — 引擎工具优先，正则 fallback | 技术债务 |

### R6: 监控与运维 (优先级: P1)

**目标**: 运行超时、磁盘管理、审计日志。

| 需求 | 描述 | 来源 |
|------|------|------|
| R6.1 | 运行超时 — 可配置 (default: 24h), 超时后自动 cancel | 痛点7 |
| R6.2 | 磁盘空间监控 — 低于阈值告警/暂停新任务 | 痛点8 |
| R6.3 | Work-dir 清理策略 — 保留策略 + 过期自动删除 + 手动 API | 痛点8 |
| R6.4 | 审计日志 — who/what/when/run_id | 合规需求 |
| R6.5 | 资源使用追踪 — CPU时间/内存峰值/磁盘使用 | 可观测性 |
| R6.6 | cleanup API — `POST /runs/{id}/cleanup` | 运维 |

### R7: 批量投递 + 通知 (优先级: P2)

**目标**: 支持一次投递多个分析，完成后通知。

| 需求 | 描述 | 来源 |
|------|------|------|
| R7.1 | 批量投递 API — `POST /runs/batch` | 批量场景 |
| R7.2 | 批次状态查询 — `GET /runs/batch/{id}` | 进度汇总 |
| R7.3 | 批量取消 — `POST /runs/batch/{id}/cancel` | 运维 |
| R7.4 | Webhook 通知 — on_complete/on_failure/on_batch_complete | 集成需求 |
| R7.5 | 通知配置 — per-project notification rules | 灵活性 |
| R7.6 | 运行配置模板 — 保存常用运行配置 | 效率 |

---

## 非功能需求

| 需求 | 描述 | 标准 |
|------|------|------|
| NF1 | 新代码测试覆盖率 | ≥ 80% |
| NF2 | 单文件行数上限 | 400行 (推荐), 800行 (硬上限) |
| NF3 | 单函数行数上限 | 50行 |
| NF4 | 不引入外部调度框架 (如 Celery) | 保持架构简洁 |
| NF5 | 保持现有 API 响应格式兼容 | 不破坏前端 |
| NF6 | 保持 SSE 事件系统兼容 | 可增加事件类型 |
| NF7 | 零外部服务依赖 (不引入 Redis/RabbitMQ/Cromwell) | 部署简单 |

---

## 依赖关系图

```
R1 (引擎抽象) ← R2 (调度器)   ← R3 (资源感知)
             ← R4 (断点重试)
             ← R5 (DAG兼容)
                R2 (调度器)   ← R6 (监控运维)
                              ← R7 (批量通知)
```

## 实现顺序

```
R1 → R2 → R4 → R5 → R3 → R6 → R7
```

理由:
1. R1 (引擎抽象) 是所有后续的基础
2. R2 (调度器) 是第二基础，资源感知和监控都依赖它
3. R4 (断点重试) 紧跟引擎抽象，因为 resume/retry 直接依赖引擎接口
4. R5 (DAG兼容) 依赖引擎抽象的工具调用能力
5. R3 (资源感知) 依赖调度器
6. R6 (监控运维) 依赖调度器
7. R7 (批量通知) 最后，依赖调度器基础设施

---

## 边界场景清单

### 高并发场景
- 用户一次投递 100 个分析: 需要批量 API + 持久化队列 + 资源感知调度
- 多个用户同时投递: 需要优先级 + 公平调度 (暂不实现配额)
- 长时运行管线 (WGS: 数天): 需要超时保护 + 断点续运

### 故障场景
- 服务重启: QUEUED/RUNNING 任务需要自动恢复
- 引擎进程被 OOM-killer 杀死: 需要检测 + 自动重试
- 磁盘空间耗尽: 需要预检 + 实时监控
- 网络中断 (下载 reference): 需要步骤级重试

### 数据场景
- 大文件输入 (单个 FASTQ 20-50GB): 路径验证不应遍历文件内容
- 多 sample 批次 (100+ samples): samplesheet 生成 + 并行执行
- 中间结果查看: 当前只支持最终 output，需要扩展

### 引擎特有场景
- Nextflow DSL2 多模块管线: include/module 跨文件解析
- nf-core 管线无本地文件: schema 需从远程获取
- WDL subworkflow: 嵌套调用链
- GPU 管线 (Parabricks): 资源探测需包含 GPU
