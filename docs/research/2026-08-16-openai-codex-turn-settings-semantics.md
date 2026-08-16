# OpenAI Codex 会话配置与 Turn 快照语义调研

日期：2026-08-16

固定上游版本：[`openai/codex@73abda8b`](https://github.com/openai/codex/tree/73abda8bfef6bd42eb11351be53980a027fd1feb)

## 调研问题

本文只依据 OpenAI 官方 Codex 仓库回答以下问题：

1. 同一 Thread 中能否修改 Model、Approval/Permission、Sandbox 和 CWD？
2. 修改何时影响正在执行的 Turn、后续 Turn 和排队消息？
3. 协议与 UI 如何表达并确认这些设置？
4. Model 切换如何影响历史连续性和 Prompt Cache？

这里的 `Thread` 指可持续多轮的会话，`Turn` 指一次从用户输入开始的 Agent
执行。源码中的 `permission profile` 是较新的权限抽象；旧接口仍保留
`approval policy + sandbox policy`。

## 结论

Codex 的设计不是“创建会话时永久冻结配置”，也不是“修改 Selector 后立即改变
正在运行的 Agent”。它采用以下规则：

```text
Thread sticky settings
  + 本次 turn/start overrides
  -> 创建不可变的 TurnContext snapshot
  -> Active Turn 始终使用该 snapshot

运行中修改 Thread settings
  -> 不改变 Active Turn
  -> 后续真正开始的 Turn 使用新 settings
```

因此，对 BioinfoFlow Q9 最忠实于 Codex 的答案是：

- Model、Permission 和执行环境 Selector 始终可以修改；
- Active Run 保持启动时快照，不被中途修改；
- 修改从下一个真正开始的 Run 生效；
- 普通排队消息不冻结 Model/Permission，出队并开始时使用最新 Thread settings；
- 每个已启动 Run 必须持久化实际生效的配置快照，供审计与历史 UI 展示。

这比“排队时冻结所有配置”更接近 Codex 当前实现，也比“立即改变 Active Run”更安全。

## 1. Model 与 Permission 可以在同一 Thread 修改

Codex v2 的 `TurnStartParams` 同时接受 `cwd`、`approvalPolicy`、
`sandboxPolicy`/`permissions`、`model` 等覆盖值。源码注释对这些字段使用同一语义：
“for this turn and subsequent turns”。也就是说，本次 Turn 使用新值，且新值会成为
后续 Turn 的 sticky setting。[`TurnStartParams`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/app-server-protocol/src/protocol/v2/turn.rs#L71-L139)

Codex 还提供独立的 `thread/settings/update`。它允许在没有发送新消息时修改 CWD、
Approval、Sandbox/Permission Profile、Model、Reasoning Effort 等，字段注释明确说明
影响 subsequent turns。[`ThreadSettingsUpdateParams`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L218-L278)

这说明 Model 与 Permission Selector 不应因为已经发过首条消息而锁死。它们是会话级
可变设置，而不是 Conversation 创建参数。

## 2. Active Turn 冻结，修改从后续 Turn 生效

Core 在接受 `turn/start` 前先验证设置。如果当前 Thread 空闲，它先把覆盖值应用到
Session Configuration，再从该 Configuration 创建新的 `TurnContext`。这个
`TurnContext` 持有该 Turn 的 Model、Permission Config、Environment Snapshot、CWD
等数据。[创建 Turn 快照](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/session/turn_context.rs#L693-L829)

`TurnContext` 的定义也明确称其为“single turn of the thread”所需上下文，并保存
Turn-scoped Config、Model、Environment Snapshot 和 CWD。[`TurnContext`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/session/turn_context.rs#L136-L180)

如果提交输入时已有 Active Turn，Codex 会把输入作为 steering 交给当前 Turn，同时
只更新 Thread 的持久设置。源码直接写明：Active Turn 保留已有 Context，更新只对
subsequent turns 生效。[`PreparedTurnInputSettings::apply_steered`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/session/turn_input.rs#L93-L138)

Turn 内部即使经历多次“模型输出—工具执行—继续采样”，每一步仍从同一个
`TurnContext` 捕获 Model、Approval、Environment 和工具配置。因此 Thread 设置更新
不会偷偷改变一个执行到一半的 Run。[`capture_step_context`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/session/mod.rs#L3111-L3221)

## 3. 排队消息不冻结 Selector 配置

Codex 的持久 Queue 协议只保存消息输入与消息 ID；`QueuedSubmission` 没有 Model、
Approval、Sandbox 或 CWD 字段。[Queue 协议](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L865-L965)

Queue 出队时使用 `TurnInputRequest::new(input)` 启动 Turn，没有附带
`ThreadSettingsOverrides`。因此新 Turn 在真正启动时从当前 Session Configuration
构造快照，而不是恢复排队时的配置。[`QueuedItemService::start`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/ext/queue/src/service.rs#L163-L225)

Codex TUI 的本地 queued user message 同样只保存消息内容和 UI action；空闲后再走正常
提交路径，所以也会采用开始执行时的最新设置。[`QueuedUserMessage`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/tui/src/chatwidget/user_messages.rs#L61-L80)；[队列出队提交](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/tui/src/chatwidget/input_flow.rs#L98-L178)

这形成一个清晰边界：

| 状态 | Model/Permission 修改结果 |
| --- | --- |
| 尚未提交的 Composer Draft | 使用提交时的最新值 |
| 已排队但尚未开始的消息 | 使用真正开始时的最新值 |
| 正在执行的 Active Turn | 保持启动时快照 |
| 下一次新 Turn | 使用最新 Thread sticky settings |

如果 BioinfoFlow 未来希望“某条排队消息固定使用排队时配置”，可以把配置快照加入 Queue
Item，但那是额外产品语义，不是 Codex 当前实现。

## 4. Protocol 与 UI 使用权威状态回显

Codex 的 `thread/settings/update` 响应只表示更新已进入处理队列，不代表客户端可以把
本地乐观值视为最终真相。源码要求：有依赖关系的局部更新应合并发送，或等待
`thread/settings/updated` 通知。[设置更新处理](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/app-server/src/request_processors/turn_processor.rs#L685-L724)

Core 成功应用设置后产生完整的 `ThreadSettingsSnapshot`，App Server 将它映射为
`thread/settings/updated` 通知。Snapshot 包含 Model、Approval、Permission Profile、
CWD、Reasoning 等实际生效值。[Core Snapshot](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/protocol/src/protocol.rs#L2041-L2065)；[App Server 通知映射](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/app-server/src/bespoke_event_handling.rs#L1190-L1207)

Codex TUI 的 Model Selector 会立刻表现用户选择，然后通过
`thread/settings/update` 同步 Active Thread；权限设置使用同一方向。
[`UpdateModel` 处理](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/tui/src/app/event_dispatch.rs#L1307-L1321)；[TUI Thread settings 同步](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/tui/src/app/thread_settings.rs#L20-L87)

对 BioinfoFlow，建议将 Selector 状态拆为：

- `requested`：用户刚选择、等待服务端确认；
- `effectiveThreadSettings`：服务端回传的权威 Thread 设置；
- `effectiveTurnSettings`：某个已启动 Run 的不可变快照。

UI 可以立即显示 pending 状态，但收到服务端确认前不能假设设置已经生效；失败时回滚并
保留错误信息。Transcript 中则显示 `effectiveTurnSettings`，避免用户后来换 Model 后，
历史 Run 看起来也跟着改变。

## 5. 历史连续性与 Prompt Cache

Codex 的默认 `prompt_cache_key` 是 Session ID，而不是 Model、Permission 或 CWD 的
组合。因此 Thread 内修改设置不会主动更换 Prompt Cache Key。
[`ModelClient::prompt_cache_key`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/client.rs#L450-L499)

官方 Prompt Caching 测试进一步验证：Thread settings override 和 per-turn override
前后使用相同 `prompt_cache_key`；旧输入保持为稳定前缀，Model Switch、Permission 和
Environment 变化以追加 Context 的方式进入历史，而不是重写 System Prompt 或 Tool
Schema。[Thread settings 缓存测试](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/tests/suite/prompt_caching.rs#L390-L479)；[Per-turn overrides 缓存测试](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/tests/suite/prompt_caching.rs#L668-L754)

需要区分两种复用：

1. **Prompt cache key 和历史前缀连续性**：Thread 内保持稳定。
2. **Responses WebSocket 的 `previous_response_id` 增量复用**：要求前后请求的 Model、
   Instructions、Tools、Reasoning、Service Tier、Prompt Cache Key 等属性一致；切换
   Model 会停止该增量复用。[请求属性匹配](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/client.rs#L305-L361)

因此 Model 切换不会破坏 canonical history，也不要求新建 Conversation；但供应商侧
某种更窄的增量续接可能自然失效。Codex 通过保留完整历史，并在 Model 变化时追加
`<model_switch>` Developer Context，使新 Model 获得自己的指令，而不重写旧消息。
[`ModelInstructionsState`](https://github.com/openai/codex/blob/73abda8bfef6bd42eb11351be53980a027fd1feb/codex-rs/core/src/context/world_state/model.rs#L1-L58)

## 对 BioinfoFlow Q9 的设计决定建议

复制 Codex 的语义边界，而不是复制其具体 TUI 组件：

1. Composer 中的 Model、Permission、Environment Selector 始终可编辑。
2. 每个 Run 开始时解析并持久化一个不可变 `TurnExecutionConfig`：
   `model`、`permissionPolicy`、`environmentScope`、`cwd`、`reasoning`。
3. Active Run 始终使用自己的 `TurnExecutionConfig`，Selector 修改不得穿透进去。
4. Selector 修改更新 Conversation/Thread sticky settings，并从下一次真正开始的 Run
   生效；排队消息默认采用开始时最新设置。
5. 服务端通过版本化 `thread.settings.updated`/Snapshot 回传权威状态；前端使用
   requested/effective 两阶段状态。
6. Transcript 渲染只读取 Run 已持久化的 effective snapshot，不读取当前 Composer
   Selector。
7. 动态 Model、Permission 和 Environment 数据不要写入稳定 System Prompt 或动态
   Tool Schema Enum；保持固定 Prompt Cache Key，并用 Turn Snapshot 与追加式 Context
   Diff 表达变化。

上述规则同时满足三个目标：用户可以像 Codex 一样随时切换设置；运行中的行为可预测、
可审计；后端 Harness 替换不会迫使前端重写会话交互语义。
