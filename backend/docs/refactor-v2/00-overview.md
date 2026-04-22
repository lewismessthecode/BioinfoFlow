# 00 — 重构总览

## 一句话结论

当前 backend 的 run 执行链路是“能工作”的，但核心问题不是某几个 bug，而是职责耦合过重。`RunService`、`TaskRunner`、`jobs.py`、引擎服务之间缺少清晰边界，导致调度、恢复、重试、资源感知、DAG 兼容性这几类需求都只能继续堆在现有实现上。

这次重构的目标不是换技术栈，而是把 run 执行部分收敛成一个稳定的子系统。

## 当前链路

```text
API /runs
  -> RunService
    -> TaskRunner (进程内内存队列)
      -> execute_run()
        -> NextflowService / MiniWDLService
          -> stdout/stderr 事件
            -> runtime/events.py
              -> SSE -> frontend
```

## 当前实现的优点

下面这些基础值得保留，不应该在重构中被打散：

1. 路径安全校验已经比较严谨。
2. 运行归档已经覆盖输入快照与 secret 脱敏。
3. SSE 事件模型已经和前端联通。
4. 双引擎支持已经存在。
5. API envelope 和前端契约已经稳定。

## 当前实现的主要问题

1. 调度器过薄。
   `TaskRunner` 只有内存队列和固定并发，无法持久化、无法恢复、无法观测。
2. 运行执行流程耦合过重。
   `execute_run()` 同时处理 DB、路径校验、引擎选择、Docker 注入、事件更新、DAG 状态、错误恢复。
3. 引擎能力没有统一抽象。
   Nextflow 和 MiniWDL 的命令构建、事件模型、取消能力、resume 能力都不一致。
4. 运行状态和运行配置耦合在 `Run.config` JSON 里。
   这会让状态更新、DAG 更新、恢复逻辑都变得脆弱。
5. 校验和 DAG 解析对复杂工作流支持不足。

## V2 的核心判断

### 1. 先拆边界，再加能力

应优先建立：

- `EngineAdapter`
- `ExecutionBackend`
- `RunScheduler`

只有这三层稳定下来，后面的自动重试、超时、资源感知、批量投递才不会继续把 `jobs.py` 写得更大。

### 2. `TaskRunner` 不应被“一刀切”删除

当前 `task_runner` 不只服务 runs，也被 image pull 使用。重构应该将 runs 迁移到专用 scheduler，而不是把所有后台异步任务都塞进同一套新机制。

### 3. WDL resume 不能和 Nextflow resume 混为一谈

Nextflow `-resume` 是引擎原生能力。
WDL 在当前架构里只能做应用层 best-effort restart assist。V2 需要把这个差异写进需求和验收标准，而不是模糊处理。

### 4. `Run.config` 需要先“收口”，再考虑彻底拆表

短期不一定要把 `Run.config` 全部拆成多张表，但至少要先建立命名空间、访问 helper 和 schema version。否则后面任何阶段都会继续扩大隐式状态。

## 目标状态

```text
API /runs
  -> RunService
    -> RunScheduler (持久化队列, 可恢复)
      -> ExecutionBackend (Local first)
        -> EngineAdapter (Nextflow / WDL)
          -> EngineEvent
            -> Run event handler
              -> SSE + DB status + DAG
```

## 推荐交付顺序

1. Phase 0: 补 seams、补 characterization tests、收口 `Run.config`
2. Phase 1: 引擎抽象
3. Phase 2: 持久化 run scheduler
4. Phase 3: 重试、超时、清理、审计的基线能力
5. Phase 4: DAG/schema 能力提升
6. Phase 5: 资源感知
7. Phase 6: 批量投递与通知

## 成功标准

重构完成后，至少应满足以下条件：

1. run 的创建、取消、恢复、重试，不再依赖 `jobs.py` 中的引擎 if/elif 分支。
2. 服务重启后，排队中的任务不会无条件丢失。
3. Nextflow 和 WDL 至少共享一套统一事件和执行接口。
4. 前端现有 API 和 SSE 使用方式保持兼容。
5. 代码结构上不再有新的千行 service 或数百行执行函数。
