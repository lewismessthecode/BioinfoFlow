# Agent Platform Terminology / Agent 平台术语

> **Superseded / 已废弃：** 本词典记录旧 Host/Engine 讨论语义。新的最小术语以
> [BioinfoFlow 完整 Agent Harness 重构计划](../plans/2026-08-13-complete-agent-harness-rearchitecture.md#最小术语)
> 为准。

This is the working bilingual vocabulary for the Agent Platform redesign. It
separates product concepts from runtime mechanisms and migration techniques so
that similar words do not become accidental synonyms.

本文是 Agent 平台重构所使用的中英双语工作词典。它把产品领域概念、运行时机制和迁移手法分开，避免相近词语被误当成同义词。

## Naming rules / 命名规则

1. Use **Tool Call** for model intent and **Tool Action** for a governed effect
   attempt. Do not use bare **Action** when either meaning is possible.
2. Use **Decision Request** for the pending question and **Decision** for its
   immutable resolution. **Approval** is one Decision kind.
3. Use **execution claim holder** instead of bare “owner” when referring to a
   worker. “Owner” remains available for product identity or access control.
4. Use **canonical** only for platform-owned semantic truth. Engine-native and
   provider-native state is never canonical product state.
5. Use **Conversation Projection** for the server-side read model and
   **Conversation Feed** for the client protocol that transports it.

## Product domain / 产品领域

### Conversation / 对话

**English:** The durable product container for related user and agent work. It
preserves semantic continuity independently of any model provider or harness.

**中文：** 承载一组相关用户与 Agent 工作的持久化产品容器。它不依赖具体模型供应商或 harness，负责保持语义连续性。

### Turn / 回合

**English:** One user-meaningful unit of work inside a Conversation. A Turn may
contain multiple engine runs, pause for decisions, and resume after actions.

**中文：** 对话中的一个用户可理解的工作单元。一个 Turn 可以包含多次 engine run，也可以因等待决策而暂停，再在动作完成后继续。

**Not:** one process invocation, one model request, or one worker attempt.

### Canonical Conversation / 规范对话

**English:** The ordered, platform-owned semantic history sufficient to start a
compatible engine without relying on provider or harness-private state. It
contains committed user messages, assistant messages, finalized Tool Calls,
and Tool Results; transient token deltas and opaque checkpoints are excluded.

**中文：** 由平台拥有、按顺序保存、足以让兼容 engine 在不依赖供应商或 harness 私有状态的情况下重新启动的语义历史。它包含已提交的用户消息、助手消息、最终 Tool Call 和 Tool Result；瞬时 token delta 与 opaque checkpoint 不属于其中。

### Tool Call / 工具调用意图

**English:** A finalized engine request to use one capability with specific
arguments. Persisting a Tool Call records intent; it does not authorize or
execute the effect.

**中文：** Engine 对某项 capability 及其具体参数形成的最终调用意图。持久化 Tool Call 只是记录意图，并不代表该外部作用已获授权或已经执行。

### Tool Action / 工具动作

**English:** One governed attempt to settle a Tool Call through validation,
authorization, optional approval, effect claim, execution, and settlement. A
Tool Call may have more than one Tool Action only when retry or reconciliation
policy explicitly permits it.

**中文：** 为完成一个 Tool Call 而进行的一次受治理尝试，涵盖校验、授权、可选审批、effect claim、执行与 settlement。只有在重试或对账策略明确允许时，一个 Tool Call 才能对应多个 Tool Action。

### Action / 动作

**English:** An overloaded informal word. In normative architecture and schema
discussion, replace it with **Tool Call**, **Tool Action**, **Effect**, or a
specific lifecycle command. If a legacy table says `AgentAction`, determine
which of these meanings it currently combines.

**中文：** 一个容易过载的非正式词。在正式架构和 schema 讨论中，应替换为 **Tool Call**、**Tool Action**、**Effect** 或具体生命周期命令。如果旧表名是 `AgentAction`，需要先判断它混合了上述哪些语义。

### Tool Round / 工具轮次

**English:** The complete set of Tool Calls emitted by one model response that
must reach host-defined resolution before the engine may continue that model
protocol.

**中文：** 一次模型响应产生的完整 Tool Call 集合；在 engine 按该模型协议继续之前，这组调用必须达到 Host 定义的解决状态。

### Decision Request / 决策请求

**English:** A durable question that suspends progress until an authorized
actor resolves it. It may concern approval, user input, plan confirmation, or
another explicitly modeled interaction.

**中文：** 一个会暂停进度、直到有权主体作出处理的持久化问题。它可以用于审批、用户输入、计划确认或其他被明确建模的交互。

### Decision / 决策

**English:** The immutable resolution of one Decision Request, including who
decided, what was decided, and which request version was resolved.

**中文：** 对某个 Decision Request 的不可变处理结果，包括决策者、决策内容以及被处理的请求版本。

### Approval / 审批

**English:** A Decision whose subject is whether a governed action may proceed.
Approval is not authorization: platform policy still determines whether the
requested action is legally callable for the current identity and scope.

**中文：** 判断某个受治理动作是否可以继续的一类 Decision。审批不等于授权：平台策略仍需判断当前身份与范围是否有权执行该动作。

### Artifact / 产物

**English:** A user-addressable product output linked to a Turn or Tool Action,
such as a file, report, dataset, image, or structured result.

**中文：** 与 Turn 或 Tool Action 关联、用户可以访问的产品输出，例如文件、报告、数据集、图片或结构化结果。

## Host and engine boundary / Host 与 Engine 边界

### Durable Agent Host / 持久化 Agent 宿主

**English:** The BioinfoFlow-owned runtime that controls durable lifecycle,
governed effects, decisions, canonical conversation, audit, recovery, and the
public conversation projection.

**中文：** 由 BioinfoFlow 拥有的运行时，负责持久生命周期、受治理的外部作用、决策、规范对话、审计、恢复以及公开对话投影。

The Host contains three deep responsibility areas:

- **Turn Lifecycle / 回合生命周期** — whether work may run, suspend, resume,
  recover, or terminalize, and which execution claim may publish.
- **Action Runtime / 动作运行时** — capability exposure, Tool Call persistence,
  Tool Action policy, approval, effect execution, settlement, audit, and
  artifacts.
- **Conversation Projection / 对话投影** — canonical facts to authoritative
  snapshots and ordered public progress.

### Agent Harness / Agent 运行框架

**English:** A reasoning runtime or framework with its own loop, provider
integration, context strategy, tool-call format, and optional native state.
Examples may include a native BioinfoFlow loop, Pydantic AI, Pi, Hermes, or a
future framework.

**中文：** 拥有自身推理循环、模型供应商集成、上下文策略、工具调用格式和可选原生状态的 Agent 运行框架，例如 BioinfoFlow Native、Pydantic AI、Pi、Hermes 或未来框架。

### Agent Engine / Agent 引擎

**English:** The Host-facing semantic role that advances reasoning, publishes
normalized progress, proposes Tool Calls or Decision Requests, and reports an
outcome. It does not own product durability or external-effect authority.

**中文：** 面向 Host 的语义角色，负责推进推理、发布规范化进度、提出 Tool Call 或 Decision Request，并报告运行结果。它不拥有产品持久化真相，也无权自行决定外部作用。

### Engine Adapter / 引擎适配器

**English:** The implementation that translates between one concrete harness
and the versioned Agent Engine contract. Harness-native events, IDs, tool APIs,
and checkpoints stop at this boundary.

**中文：** 在某个具体 harness 与带版本的 Agent Engine 契约之间进行转换的实现。Harness 原生事件、ID、工具 API 与 checkpoint 必须止步于该边界。

### Engine Contract or Engine SPI / 引擎契约或引擎 SPI

**English:** The versioned semantic interface implemented by every Engine
Adapter. It defines starts, progress, tool-round requests and results, decision
requests and resolutions, control signals, checkpoints, outcomes, and failure
rules without exposing ORM or transport internals.

**中文：** 每个 Engine Adapter 都必须实现的带版本语义接口。它定义启动、进度、工具轮次请求与结果、决策请求与处理、控制信号、checkpoint、结果与失败规则，但不暴露 ORM 或传输层内部实现。

### Model Grant / 模型授权凭据

**English:** A Host-issued authorization package describing which model target,
credential handle, quota, billing identity, and fallback policy an engine may
use. It is not necessarily a universal model invocation API.

**中文：** Host 发放的模型使用授权包，说明 engine 可以使用的模型目标、凭据句柄、配额、计费身份与 fallback 策略。它不必等同于一个强制统一的模型调用 API。

### Engine Checkpoint / 引擎检查点

**English:** Opaque, adapter-private state tagged with engine ID, engine
version, and schema version. It may accelerate same-engine resume but is never
the only semantic source of truth and is not portable across engines.

**中文：** 带有 engine ID、engine version 与 schema version 的 opaque 适配器私有状态。它可以加速同一 engine 的恢复，但绝不能成为唯一语义真相，也不保证跨 engine 可移植。

## Durability and effects / 持久化与外部作用

### Engine Run / 引擎运行

**English:** One invocation or resumable interaction between the Host and an
Engine Adapter for a Turn. A Turn may contain multiple Engine Runs.

**中文：** Host 与某个 Engine Adapter 围绕一个 Turn 进行的一次调用或可恢复交互。一个 Turn 可以包含多个 Engine Run。

### Execution Claim / 执行权声明

**English:** The Host record granting one worker generation the temporary right
to advance and publish state for an Engine Run or Turn lifecycle step.

**中文：** Host 记录的一项临时执行权，允许某一代 worker 推进一个 Engine Run 或 Turn 生命周期步骤并发布状态。

### Owner / 所有者

**English:** Do not use this word alone. A **Conversation Owner** is a product or
authorization identity. A legacy **Turn Owner** is actually the current
**Execution Claim Holder** and should be renamed; it does not own the user's
conversation or its data.

**中文：** 不要单独使用这个词。**Conversation Owner（对话所有者）**属于产品身份或授权语义；旧有的 **Turn Owner** 实际表示当前 **Execution Claim Holder（执行权持有者）**，应予以改名，它并不拥有用户的对话或数据。

### Lease / 租约

**English:** The expiry-bounded lifetime of an Execution Claim. A lease prevents
permanent ownership after a worker disappears; it does not by itself prevent a
stale worker from writing.

**中文：** Execution Claim 带过期时间的有效期。Lease 防止 worker 消失后永久占有执行权，但仅有 lease 并不能阻止旧 worker 写入。

### Fencing Token or Claim Generation / 隔离令牌或声明代次

**English:** A monotonically changing token checked on every protected write so
that a stale worker cannot publish after its lease was replaced.

**中文：** 在每次受保护写入时校验、单调变化的 token，用来阻止旧 worker 在其 lease 被替换后继续发布状态。

### Effect / 外部作用

**English:** A change outside the Host transaction boundary, such as running a
shell command, writing a remote file, launching a workflow, or calling an
external API.

**中文：** 发生在 Host 数据库事务边界之外的变化，例如执行 shell 命令、写远端文件、启动工作流或调用外部 API。

### Effect Intent / 外部作用意图

**English:** The durable record written before an Effect becomes eligible to
execute, including its idempotency and replay policy.

**中文：** 在 Effect 获准执行之前写入的持久化记录，其中包括幂等与重放策略。

### Effect Claim / 外部作用执行权

**English:** The temporary, fenced right for one worker to attempt one Effect.

**中文：** 某个 worker 尝试执行一次 Effect 的临时、受 fencing 保护的权利。

### Settlement / 结算

**English:** The durable terminal record of what is known about an Effect:
completed, rejected, failed, cancelled before execution, or uncertain.

**中文：** 对某个 Effect 已知终态的持久化记录：已完成、已拒绝、失败、执行前取消，或结果不确定。

### Reconciliation Required / 需要对账

**English:** The state used when the Host cannot prove whether a non-idempotent
Effect occurred. It forbids blind automatic replay and requires a tool-specific
reconciliation or human decision.

**中文：** 当 Host 无法证明一个非幂等 Effect 是否已经发生时使用的状态。它禁止盲目自动重放，要求工具特定的对账流程或人工决策。

## Events, replay, and read models / 事件、回放与读模型

### Event Ledger / 事件账本

**English:** An append-only, ordered record of Host-owned facts and progress
observations used for audit, recovery coordination, and replay. It is not the
sole write-model authority for current Turn, Tool Call, or Tool Action status.

**中文：** Host 所拥有事实与进度观察的追加式有序记录，用于审计、恢复协作与回放。它不是 Turn、Tool Call 或 Tool Action 当前状态的唯一写模型真相。

### Audit Entry / 审计条目

**English:** Structured, append-only evidence explaining a policy evaluation,
decision, effect attempt, settlement, or administrative change.

**中文：** 用于解释策略评估、决策、外部作用尝试、settlement 或管理变更的结构化追加式证据。

### Conversation Projection / 对话投影

**English:** The rebuildable server-side read model derived from canonical facts
and retained ledger observations for efficient product display.

**中文：** 从规范事实与保留的 ledger 观察中派生、可重建、便于产品高效展示的服务端读模型。

### Projection Snapshot / 投影快照

**English:** An authoritative representation of the Conversation Projection
through an exact sequence watermark, `snapshot_seq`.

**中文：** 截止到精确序列水位 `snapshot_seq` 的权威 Conversation Projection 表示。

### Conversation Feed / 对话流

**English:** The versioned client protocol composed of an authoritative
Projection Snapshot plus typed, ordered progress after `snapshot_seq`.

**中文：** 面向客户端的带版本协议，由权威 Projection Snapshot 与 `snapshot_seq` 之后的类型化、有序进度组成。

### Replay Cursor / 回放游标

**English:** The last applied ledger or feed sequence used to request strictly
later events after reconnect. The cursor is a sequence number, not an event UUID
or timestamp.

**中文：** 重连后用于请求严格晚于某位置事件的最后已应用 ledger/feed 序号。Cursor 是序列号，不是事件 UUID 或时间戳。

### Retained-event Floor / 事件保留下界

**English:** The oldest sequence still available for incremental replay. If a
cursor is older, the protocol returns `reset_required` with a fresh snapshot
location instead of silently returning incomplete history.

**中文：** 仍可用于增量回放的最早序号。如果 cursor 早于该下界，协议应返回带新快照位置的 `reset_required`，而不能静默返回不完整历史。

## Architecture and migration / 架构与迁移

### Seam / 可替换边界

**English:** A deliberately narrow boundary where one implementation can be
replaced without changing the consumers on the other side, verified by contract
and conformance tests.

**中文：** 一个经过刻意收窄的边界，使一侧实现可以在不修改另一侧消费者的情况下被替换，并由契约与一致性测试验证。

### Strangler Migration / 绞杀式迁移

**English:** A migration strategy that routes slices of behavior from a legacy
system to a replacement until the legacy path has no remaining reachability and
can be deleted.

**中文：** 将行为切片逐步从旧系统导向新系统，直到旧路径不再可达并可被删除的迁移策略。

### Locality / 位置属性

Do not use this word alone. Use one of these precise terms:

- **Execution Locality / 执行位置** — where an engine or Effect runs: backend
  process, sidecar, local host, remote SSH host, or another worker.
- **Data Locality / 数据位置** — where required data is physically available.
- **Checkpoint Affinity / 检查点亲和性** — which engine implementation or
  runtime location can read an opaque Engine Checkpoint.

### Conformance Suite / 契约一致性测试套件

**English:** A provider-independent set of traces every Engine Adapter must
pass, including streaming, tool rounds, decisions, cancellation, duplicate
delivery, crash recovery, and restart without a checkpoint.

**中文：** 每个 Engine Adapter 都必须通过的供应商无关测试轨迹集合，包括流式输出、工具轮次、决策、取消、重复投递、崩溃恢复以及无 checkpoint 重启。

## Harness replaceability levels / Harness 可替换等级

“Pluggable” is not a single guarantee. BioinfoFlow should state four levels:

| Level | Guarantee | 中文含义 |
| --- | --- | --- |
| R1 — Next-Turn Replaceable | A different compatible engine may handle the next Turn from Canonical Conversation. | 下一 Turn 可换 engine。 |
| R2 — Barrier Replaceable | At a durable Tool/Decision barrier, another compatible engine may continue the same Turn from canonical facts and resolved results. | 在工具或决策持久化屏障处，同一 Turn 可换 engine。 |
| R3 — Same-Engine Resumable | The same engine/version may resume faster from its opaque checkpoint. | 同一 engine/version 可用私有 checkpoint 快速恢复。 |
| R4 — Live Cross-Engine Migratable | An in-flight model stream can move to a different engine without returning to a durable barrier. | 正在进行的模型流可无缝迁移到另一 engine。首版不承诺。 |

The redesign should guarantee R1 and R2, support R3 as an optimization, and
explicitly defer R4. A harness is replaceable only if its adapter passes the
contract and can rebuild from Canonical Conversation; an arbitrary framework
cannot be dropped in without an adapter.

重构应保证 R1、R2，把 R3 作为优化支持，并明确暂缓 R4。只有当某个 harness 的 adapter 通过契约测试且能从 Canonical Conversation 重建时，它才是可替换的；任意框架都不能在没有 adapter 的情况下直接插入。

## One complete example / 一个完整示例

1. The engine emits a finalized `run_command` **Tool Call** with an engine-local
   correlation key.
2. The Host persists a canonical Tool Call before any Effect is eligible.
3. Action Runtime creates a **Tool Action**, evaluates authorization, and may
   create an approval **Decision Request**.
4. An immutable **Decision** resolves that request. Approval still does not
   bypass authorization.
5. The Host persists Effect Intent, grants a fenced Effect Claim, executes the
   command, and writes Settlement plus any **Artifacts** and **Audit Entries**.
6. The normalized Tool Result enters Canonical Conversation and is returned to
   the engine using its correlation key.
7. Conversation Projection updates; the client receives a snapshot/upsert with
   an ordered sequence. The frontend does not infer these states from tool names
   or engine-native events.
