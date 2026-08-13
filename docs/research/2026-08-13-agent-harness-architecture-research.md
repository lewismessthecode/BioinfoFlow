# Agent Harness 可替换架构：开源项目一手资料调研

- 调研日期：2026-08-13
- 调研范围：官方 GitHub 仓库中的源码与一方文档
- 关注问题：可替换 harness seam、规范化事件、工具模型、持久化与恢复、审批、插件以及前端协议
- 非目标：本文不设计 BioinfoFlow 的具体 interface，也不把参考项目的类型直接移植为方案

## 调研快照

| 项目 | 默认分支 | 固定提交 | 本文中的主要价值 |
| --- | --- | --- | --- |
| [earendil-works/pi](https://github.com/earendil-works/pi) | `main` | [`581d75a89cea21e50d6a26df840352f94427f633`](https://github.com/earendil-works/pi/commit/581d75a89cea21e50d6a26df840352f94427f633) | 小型 session runtime seam、domain/wire 分离、权威 snapshot 与瞬态 progress |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | `main` | [`2c7756caf2657dc074389e6edd058827ea8a7752`](https://github.com/NousResearch/hermes-agent/commit/2c7756caf2657dc074389e6edd058827ea8a7752) | 已落地的 foreign harness projector、工具注册与暴露分离、审批 transport |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | `main` | [`644815f9e5bc52ad8f7a5227a456227e9c3e639b`](https://github.com/langchain-ai/langgraph/commit/644815f9e5bc52ad8f7a5227a456227e9c3e639b) | checkpoint seam、可恢复 interrupt、带顺序的事件 envelope、工具执行 wrapper |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | `main` | [`f748e81ec64aff78c4d41593ed51803d8b15b9ee`](https://github.com/pydantic/pydantic-ai/commit/f748e81ec64aff78c4d41593ed51803d8b15b9ee) | toolset wrapper、deferred tool/approval、独立 UI protocol adapter、外置 durability |

这四个项目不是同一成熟度、同一产品形态。Pi 的新 durable harness 仍有明显未实现部分；LangGraph v3 streaming 明确标为 experimental；Pydantic AI 的持久化依赖外部 durable runtime；Hermes 已有大量产品能力，但其原生 `AIAgent` 仍是宽而重的实现。本文只提取被源码支持的模式。

## 跨项目结论

### 1. 最稳定的 seam 位于“产品 session runtime”，而不是某个 loop 的内部对象

Pi 当前最有价值的 interface 是 `PiServerService` 与 `PiSessionRuntime`：前者只负责列出、创建和打开 session；后者暴露 snapshot、phase、prompt、steer、abort、模型切换、订阅与释放。持久化 implementation、传输和内部 agent loop 都没有进入这个 interface。[源码](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/server/src/types.ts#L24-L60)

Pi server 进一步明确：应用提供 `PiServerService` implementation，server 自己负责 transport/protocol 生命周期；session metadata 也与已 acquire 的 runtime state 分开。[文档](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/server/README.md#L7-L40)

LangGraph 提供了另一个方向的实证：`RemoteGraph` 满足与本地图相同的 `PregelProtocol`，可以像本地图一样调用，说明本地与远端 harness 可以共享 seam。[协议](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/pregel/protocol.py#L25-L105) [远端 adapter](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/pregel/remote.py#L118-L163) 但 `PregelProtocol` 同时包含图结构、状态历史、更新和多种调用方式，interface 很宽；它证明“远端 adapter 可行”，不证明这个具体 interface 适合通用 agent 产品。

Hermes 的 Codex app-server 集成则是最直接的落地证据：一个 foreign runtime 绕过 native loop，adapter 消费 Codex notification，projector 把 completed item 转成 Hermes 可理解的 transcript/result，并把实时 delta 与 tool 生命周期桥接到既有 UI。[session adapter 说明](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/agent/transports/codex_app_server_session.py#L1-L23) [event projector](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/agent/transports/codex_event_projector.py#L1-L27) [归一化结果](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/agent/codex_runtime.py#L921-L949)

可复用模式：

- 产品持有 session/run 生命周期和公开状态。
- 每种 harness 通过 adapter 接入。
- adapter 负责输入映射、native event 投影和 outcome 归一化。
- 不让调用方理解 harness 的 graph、callback、provider 或 ORM implementation。

反面证据也很清楚：Hermes 当前仍通过硬编码 `api_mode` 分支选择 Codex runtime，[源码](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/agent/conversation_loop.py#L1626-L1638)；原生 `AIAgent` 构造和 callback surface 很宽，[源码](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/run_agent.py#L412-L512)。应复用 projector 思路，而不是复制这个对象形状。

### 2. Harness-native event、durable state 与 frontend protocol 应是三个不同层次

Pi 对这一点表达最严格：protocol 文档声明 session/server snapshot 是权威状态，progress 只是瞬态 UI hint，不能被 reducer 当成权威状态。[文档](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/protocol/README.md#L1-L16)

其 transcript protocol 使用封闭 discriminated unions：assistant 有 `streaming/complete/error/aborted` 状态，tool 有 `running/complete/error` 状态；incremental progress 只有 `item_started`、`assistant_delta`、`item_updated`、`item_finished`。[schema](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/protocol/src/schemas.ts#L120-L231) wire event 也仅包含 server snapshot、session snapshot、session progress 与 session removed。[schema](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/protocol/src/schemas.ts#L400-L445)

Pi 还刻意让 `pi-ai` domain objects 与 wire DTO 独立，由 server bridge 做穷尽映射、关联校验和 diagnostics 清洗。[文档](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/server/README.md#L46-L50) 这类 bridge 是防止 provider/harness 类型穿透到前端的真实 Module。

Hermes 的 gateway streaming 也明确记录了从 callback fan 迁移到小型 typed event vocabulary 的原因：事件只描述“发生了什么”，adapter 决定“如何展示”；presentation stream 不等于 conversation history。[源码与设计说明](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/gateway/stream_events.py#L1-L32) 事件 union 包含 message chunk/stop、commentary、tool start/finish 与 notice。[源码](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/gateway/stream_events.py#L41-L170)

LangGraph v2 同样使用 `{type, ns, data}` 的 discriminated stream part；消息 partial/complete、checkpoint、task、custom、debug 各自独立。[schema](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/sdk-py/langgraph_sdk/schema.py#L730-L872) 新 v3 为所有 raw stream part 增加统一 `ProtocolEvent` envelope，并明确 `seq` 才是跨事件总顺序，wall-clock timestamp 不是。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/stream/_types.py#L14-L42) 但该 v3 interface 仍被标记为 experimental。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/stream/run_stream.py#L36-L55)

Pydantic AI 则显式建议 frontend 通常不要直接消费 `ModelRequest` 和 native `AgentStreamEvent`，而是通过独立 `UIAdapter` / `UIEventStream` 转成 AG-UI、Vercel AI 或其他协议。[文档](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/docs/ui/overview.md#L1-L20)

可复用模式：

- native event：服务 harness implementation 与调试。
- canonical durable event/state：服务恢复、审计、回放和平台规则。
- public transcript/progress protocol：服务客户端与 renderer。
- 一个明确的 projector/adapter Module 完成跨层映射。
- 顺序、相关 ID、terminal status 和 replay 语义必须由 protocol 明确定义。

### 3. 工具需要拆成“注册、暴露策略、执行”三个变化轴

Pi 的 shipping `AgentTool` 包含参数 schema、参数兼容预处理、可取消执行、partial result update，以及 per-tool 串行/并行策略；结果把发送给模型的 content 与给日志/UI 的 structured details 分开。[源码](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/agent/src/types.ts#L360-L409) 它的 loop event 只暴露 tool execution start/update/end，并以 `toolCallId` 关联。[源码](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/agent/src/types.ts#L421-L443)

Hermes 的 registry 管理 handler、schema、availability 和 generation snapshot；toolset 决定具体 session/scenario 暴露哪些工具；override 需要显式授权。[registry](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/tools/registry.py#L414-L469) [override policy](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/tools/registry.py#L590-L644) [toolsets](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/toolsets.py#L29-L74)

Pydantic AI 的 `AbstractToolset` 只要求列举工具和调用工具，并允许 wrapper 组合 filter、prefix、prepare、rename、approval-required 与 deferred-loading。[源码](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/pydantic_ai_slim/pydantic_ai/toolsets/abstract.py#L76-L244) `ApprovalRequiredToolset` 本身只是一个窄 wrapper：在未批准且策略命中时抛出 `ApprovalRequired`，否则继续 inner toolset。[源码](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/pydantic_ai_slim/pydantic_ai/toolsets/approval_required.py#L15-L32)

LangGraph 的工具流提供 `tool-started`、`tool-output-delta`、`tool-finished`、`tool-error`，统一通过 `tool_call_id` 关联，并保证 inline callback ordering。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/pregel/_tools.py#L35-L50) [事件 payload](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/pregel/_tools.py#L142-L200)

可复用模式：

- Registry：工具身份、schema、metadata 与 implementation 查找。
- Exposure/Capability Policy：当前 run 可见和可调用哪些工具。
- Executor：参数校验、policy/approval、sandbox/target、执行、timeout、result normalization。
- Tool result 同时有 model-facing content 与 product-facing details，但两者不应混为一个无结构字符串。
- 工具 author 不应被迫了解 session ORM、lease token 或 frontend DTO。

### 4. Approval 是产品持有的 durable control state，不只是一个 UI callback

Pydantic AI 把需要批准或外部执行的工具统一建模为 deferred tool。resolver 可在进程内处理，也可以结束当前 run，向外返回 `DeferredToolRequests`；外部收集结果后，用原 history 和 `DeferredToolResults` 启动一个新 run，并通过 `conversation_id` 关联，不能复用原 `run_id`。[文档](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/docs/deferred-tools.md#L1-L29)

它还发出专门的 `DeferredToolRequestsEvent`，让 stream consumer 知道哪些 tool call 正在等待交互。[源码](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/pydantic_ai_slim/pydantic_ai/messages.py#L3975-L3997) 但官方文档也明确警告：如果 approval/result 由客户端连同完整 history 提交，approval 不是对恶意客户端的 authorization boundary；敏感动作仍须根据服务端认证身份授权，或由服务端持久化 paused run。[文档](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/docs/ui/overview.md#L97-L114)

LangGraph 的 `interrupt(value)` 会创建可恢复暂停，恢复必须使用 `Command(resume=...)`，并且 node 从头重新执行，所以 interrupt 之前的 side effect 必须可重放或幂等；checkpointer 是必要条件。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/types.py#L798-L824) [interrupt 语义](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/types.py#L851-L871)

Hermes 的 approval transport 分离了 host policy 与 presentation：immutable/redacted request 经 transport 展示，response 通过 request ID/digest 关联，timeout、异常或 stale response 都 fail closed。[contract](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/approval_transport.py#L1-L6) [request/decision](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/approval_transport.py#L27-L112) [fail-closed invocation](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/approval_transport.py#L133-L215) 但其 builtin pending/session approval 仍是 process-memory map/queue，不能证明 crash-durable approval。[源码](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/tools/approval.py#L2525-L2602)

Pi 则反向证明 approval 不应由 harness 假定：项目明确不内建 permission system，默认使用启动进程的权限。[README](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/README.md#L38-L46) 因此产品若需要审批、policy 与审计，不能依赖每个 harness 都原生提供相同语义。

可复用模式：

- policy/authorization 属于 host platform。
- approval request/decision 是带身份、关联 ID 和 terminal status 的 control state。
- UI 只是一种 approval transport adapter。
- timeout、失联和未知 decision 默认拒绝。
- resume 规则必须明确：是恢复同一 operation，还是创建关联的新 run。
- side effect replay policy 必须在暂停与恢复模型里显式存在。

### 5. Durability 应有独立 storage/checkpoint seam，并显式声明外部 effect 的不确定窗口

LangGraph 的 `BaseCheckpointSaver` 是真实 storage seam，提供 get/list/put/put_writes/delete，并以 `thread_id` 作为恢复、interrupt 与 time-travel 的主键。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/checkpoint/langgraph/checkpoint/base/__init__.py#L176-L206) [interface](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/checkpoint/langgraph/checkpoint/base/__init__.py#L227-L329) durability policy 也显式区分 `sync`、`async` 和 `exit`。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/types.py#L89-L105)

Pydantic AI 没有把一种 durable runtime 固化到 agent 内部，而是支持 Temporal、DBOS、Prefect、Restate 等多个 integration；其中 Restate 只依赖公开 interface，官方把它视为其他 durable system integration 的参考。[文档](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/docs/durable_execution/overview.md#L1-L16)

Pi 新 harness 规格提供了很有价值的恢复模型：conversation entry、mutable register、usage ledger 三类 store；每一步覆盖完整 `op.state` 作为 durable program counter；provider/tool external effect 使用 intent commit → effect → settlement commit 的“effect sandwich”。[规格](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/agent/docs/harness.md#L80-L137)

但必须强调成熟度：当前 `AgentHarness.create()` 遇到 restore 直接抛 `HarnessNotImplemented`，prompt、compact、resume、abort、steer 等主要行为也未实现。[源码](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/agent/src/harness/agent-harness.ts#L305-L420) 这些设计只能作为规格参考，不能作为生产验证证据。

Hermes 的 SQLite session store 已实际承担 transcript、usage、routing、compression lock 与 async delegation，使用 WAL 和原子 batch writes。[schema](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_state_common.py#L198-L350) [atomic batch](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_state.py#L7781-L7804) 但 message schema 中包含 provider/Codex-specific 字段，说明“持久化已经存在”不等于“持久化 schema 已与 harness 解耦”。

可复用模式：

- 产品 canonical transcript/event 与 harness-native checkpoint 分开存储。
- harness checkpoint 可作为 opaque、带 adapter/version 的 payload。
- 每个 external effect 必须有显式 replay/idempotency policy。
- durability level 是 policy，而不是隐藏的实现细节。
- 审计 event log、当前 operation state 与投影 read model 不要混成一个表或一个 JSON snapshot。

### 6. 插件应按能力类别设计 interface，不应暴露一个无所不包的 PluginContext

Hermes 提供最广的插件样本：tools、hooks、provider、context engine、approval transport、namespaced config/state 和 event bus 都可注册；manifest 还声明 capability 与依赖。[manifest](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/plugins.py#L397-L471) [PluginContext](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/plugins.py#L995-L1235) [event bus](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/hermes_cli/plugins.py#L2199-L2273)

其 middleware 把 read-only observer 与 behavior-changing wrapper 分开，并明确 LLM/tool request middleware、execution middleware 的执行顺序；tool request rewrite 发生在 guardrail 与 approval 之前。[文档](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/docs/middleware/README.md#L1-L21) [执行顺序](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/docs/middleware/README.md#L79-L111) observer contract 则要求稳定 correlation IDs、sanitized payload 和 fail-open telemetry callback。[文档](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/docs/observability/README.md#L1-L15) [IDs](https://github.com/NousResearch/hermes-agent/blob/2c7756caf2657dc074389e6edd058827ea8a7752/docs/observability/README.md#L65-L83)

Pi 的 extension surface 同样很广，并可注册工具、生命周期 interception、命令、UI、持久化与 renderer；这说明扩展需求真实存在，但也意味着 extension interface 很容易把 UI 与 engine 紧密绑回一起。[文档](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/coding-agent/docs/extensions.md#L3-L29)

LangGraph 的 `StreamTransformer` 是更窄的 extension seam：声明所需 raw modes，把 canonical event 转成 derived projection，支持排序、同步/异步与 suppression。[源码](https://github.com/langchain-ai/langgraph/blob/644815f9e5bc52ad8f7a5227a456227e9c3e639b/libs/langgraph/langgraph/stream/_types.py#L44-L115)

可复用模式：

- harness adapter、tool provider、policy middleware、observer、renderer extension、model provider 应是不同 interface。
- observer 默认 fail-open；authorization/policy 不能 fail-open。
- extension payload 要有局部 schema/version 与命名空间。
- override 必须显式授权，不能因名字冲突静默覆盖。
- 插件不应获得 ORM session、全局 secret map 或完整 runtime object 作为默认上下文。

## 项目逐项判断

### Pi

最值得参考：

- `PiServerService` / `PiSessionRuntime` 的小 interface。
- snapshot authoritative、progress transient 的前端协议规则。
- domain object 与 wire DTO 的穷尽 bridge。
- tool model 中 model content 与 UI details 分离。
- storage backend 与 core package 分离。
- 新 durable harness 规格中的 durable program counter 与 effect sandwich。

不可直接采用：

- experimental protocol/server 的稳定性承诺不足。[文档](https://github.com/earendil-works/pi/blob/581d75a89cea21e50d6a26df840352f94427f633/packages/server/README.md#L1-L5)
- 新 durable harness 的核心行为尚未实现。
- Pi 不提供 BioinfoFlow 所需的内建 permission/approval platform。
- coding-agent extension surface 含 UI/TUI 语义，不适合作为通用 harness interface。

### Hermes Agent

最值得参考：

- Codex app-server 的 foreign harness adapter + event projector。
- presentation event 与 persistent history 的明确分离。
- Registry → toolset/exposure → executor 的结构。
- approval policy 与 approval transport 分离。
- middleware 与 observer 的职责分离。

不可直接采用：

- 宽大的 `AIAgent` 与 callback fan。
- foreign runtime 仍由硬编码分支选择。
- frontend protocol 部分 event type/payload 仍较开放。
- transcript schema 混入 provider-specific 字段。
- pending approval 主要是 process-memory state。
- 单一 PluginContext 覆盖太多能力类别。

### LangGraph

最值得参考：

- 本地与远端 runtime 共享 interface 的 adapter 证明。
- checkpoint saver seam 与显式 durability policy。
- interrupt/resume 的持久化约束与重放警告。
- tool lifecycle event 与 correlation ID。
- ordered canonical event envelope 与 projection transformer。

不可直接采用：

- Pregel graph/channel/state vocabulary 不应成为普通 agent 产品的公开 interface。
- `PregelProtocol` 表面过宽。
- v3 streaming 仍是 experimental。
- rich `UIMessage` 适合可选 artifact，不适合让普通 transcript 绑定后端 renderer 名称或 props。

### Pydantic AI

最值得参考：

- Toolset 的 wrapper composition。
- deferred tool 同时表达 approval 和 external execution。
- UI protocol adapter 与 native events 分离。
- durability 作为可附加 capability 或外部 wrapper，而不是单一内建实现。
- 明确区分 conversation identity 与单次 run identity。

不可直接采用：

- `AbstractAgent.run()` 参数面很宽，不适合作为产品级替换 seam。[源码](https://github.com/pydantic/pydantic-ai/blob/f748e81ec64aff78c4d41593ed51803d8b15b9ee/pydantic_ai_slim/pydantic_ai/agent/abstract.py#L346-L620)
- UI adapter 默认接受 client-supplied history 的信任模型不适合直接用于高权限工具平台。
- approval 若只依靠客户端提交结果，不构成 authorization。
- 多种 durability integration 的能力与限制并不一致，不能假设一套无损统一语义。

## 对后续架构工作的证据约束

后续重构计划至少应满足以下由一手资料共同支持的约束：

1. 替换 harness 时，不应要求 frontend、ORM model 或 tool implementation 随之重写。
2. 产品必须拥有 canonical session/run/tool/approval identity；harness-native ID 只能映射或放入 extension payload。
3. public transcript/progress protocol 必须是封闭、可验证、可排序和可回放的语义模型。
4. snapshot 与 progress 的权威关系必须明确，不能让 frontend 用 transient delta 猜 durable terminal state。
5. tool registry、exposure policy、approval/authorization 与 execution 是不同 Module。
6. approval 必须持久化并 fail closed；approval UI 只是 transport Adapter。
7. 外部 effect 的 replay/idempotency 规则必须显式存在，不能由恢复代码猜测。
8. durable platform state 与 harness-native checkpoint 必须分层；native checkpoint 应有 adapter/version 标识。
9. 插件 seam 应按能力类别拆分，并为 override、schema evolution、failure policy 和资源访问设定独立规则。
10. 参考项目中的 experimental、未实现或 provider-specific 设计不能被当成已验证的生产契约。

## 来源完整性说明

本文没有使用 DeepWiki、博客、新闻稿或第三方架构解读作为结论依据。所有事实均回链到上述四个官方仓库在固定提交上的源码或仓库内一方文档。仓库后续可能变化，执行具体重构前应重新核验默认分支 HEAD 与相关文件。
