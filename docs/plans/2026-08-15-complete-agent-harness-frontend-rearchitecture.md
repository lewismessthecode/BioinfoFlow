# BioinfoFlow 完整 Agent Harness 前端重构计划

## 状态

本计划是 `2026-08-13-complete-agent-harness-rearchitecture.md` 的前端完成篇，
同时包含新前端真正需要的少量后端公开协议修正。

它不是旧 Agent 页面换皮，也不建设兼容层。完成后正式 `/agent` 只使用新的
Session / Run / Entry / typed parts / snapshot / commands / events 协议，旧
Agent Core、旧 Turn/Event 投影、Action/Decision 状态和 replay cursor 全部删除。

## 目标

> 用户看到的是一个类似 Codex 和 Claude Code 的现代 Agent 工作台：可以自然对话，
> 看见流式回复、思考摘要、计划、进度、工具执行、审批和最终结果；页面刷新后仍能
> 回到权威状态。前端只渲染后端明确表达的事实，不理解 Harness 私有实现。

这次重构必须一次性完成：

- 永久对话历史和当前运行状态的直接渲染；
- 助手正文与思考摘要的 streaming；
- 结构化计划、运行进度和执行轨迹；
- 单个工具卡片和具有真实执行方式的 Activity Group；
- Ask User、Approval 和 Recovery 三类用户交互；
- composer 内的审批权限菜单；
- 附件、文件、目录、工作流和 Run 上下文引用；
- 复制、结束时间、停止、自动滚动和回到底部等完整交互；
- Snapshot 恢复、SSE 重连、重复和乱序事件归并；
- 桌面、移动端、键盘、焦点、减少动态效果和错误状态；
- 无真实模型密钥的确定性浏览器端到端测试；
- 旧协议、旧 renderer、旧 mock 和死代码的彻底删除。

## 第一性原理

### 前端只回答三个问题

```text
这是什么会话？
已经发生了什么？
现在正在做什么？
```

对应唯一状态：

```text
SessionSnapshot
├── session
├── runs                    # 每次历史 Run 的开始、结束、状态和耗时
├── entries                 # 永久历史
└── active_run              # 仅表示未结束的当前运行，可为空
    ├── run
    ├── assistant_draft
    ├── tool_progress
    └── pending_interaction
```

前端不理解 lease、checkpoint、compression state、provider continuation、
模型重试、工具调度和恢复策略。

### 公开协议必须可直接渲染

后端不得把 provider 私有 JSON、任意 `dict` 或需要前端猜测的半成品暴露给 UI。
工具类别、工具状态、关联 ID、交互类型、时间和错误都必须使用明确字段表达。

### 永久历史与实时状态分开

- `entries` 表达已经完成且可长期重放的事实；
- `active_run` 表达尚未完成的草稿、工具进度和待处理交互；
- 正式 entry 到达后，前端按稳定 ID 清除相应草稿或临时进度；
- 删除 checkpoint 后，历史仍然完整可渲染。

### Activity Group 是视图，不是新领域模型

同一次模型响应产生的工具调用已经共同属于一条 assistant entry。前端直接以这条
entry 为组：

- 一个调用显示单张工具卡片；
- 两个或更多调用显示一个 Activity Group；
- 组内可按后端提供的 `category` 分节；
- 组标题只使用后端提供的 `execution_mode: parallel | serial | mixed`，不把多个调用
  自动解释成并行；
- 工具结果只通过 `call_id` 关联；
- 不增加 Tool Batch 表、Activity 数据库或第二套状态机；
- 不根据工具名和命令文本猜分类。

### 权限菜单表达“什么时候询问用户”

composer 保留三种清晰模式：

| 模式 | 用户语义 | Harness 行为 |
| --- | --- | --- |
| `ask_changes` | 先询问我 | 修改文件、外部网络和其他副作用前询问 |
| `ask_dangerous` | 安全操作自动完成 | 只对风险操作询问 |
| `full_access` | 工作区内自动执行 | 不做产品层软确认，但仍受沙箱、路径、网络、认证和服务端硬限制 |

当前 `read_only` 把“是否允许写入”和“什么时候确认”混在一起，不再作为 composer
审批模式。硬读写能力单独保存为：

```text
workspace_access: read_only | read_write
```

旧只读 Session 迁移为 `permission_mode=ask_changes + workspace_access=read_only`；前端只在
产品确实允许切换硬访问范围时展示该设置，不能用审批菜单绕过只读。三种审批模式必须
由 ToolExecutor 对 edit、write、bash、网络及其他副作用工具统一执行，不只是 Bash 的文案
映射。`full_access` 仍不能越过沙箱、Workspace、认证或平台禁止的操作。

权限模式在新 Session 创建前作为 composer 草稿保存；已有 Session 仅在没有活动 Run
时允许修改。修改不能自动批准或拒绝已经存在的 interaction。

### 不为未来 Harness 建设前端 Adapter

前端只消费 BioinfoFlow 的产品协议。未来接入 Pi、Hermes 或其他 Harness 时，增加一个
具体的后端接入实现，把它的输出整理为相同公开语义；前端不感知 Harness 名称、版本
或私有 checkpoint。

## 设计语言

### 视觉方向

- 体裁：`modern-minimal`；
- 页面形态：`Workbench`；
- 气质：克制、技术型、可信；
- 继续使用现有 Notion-neutral / Codex-like 设计变量；
- 保留 Avenir Next / 中文系统字体和 Geist Mono，不引入新字体依赖；
- 不增加渐变、霓虹、玻璃拟态、重阴影或展示型永动动画；
- 动态只用于表达 streaming、运行、展开收起、状态变化和位置变化；
- 所有动态支持 `prefers-reduced-motion`。

### 页面结构

保留正式 `/agent` 路由、应用导航、项目上下文和右侧 BioinfoFlow LiveDeck 外壳，
重写中间 Agent 工作区：

```text
AgentPage
└── AgentWorkbench
    ├── ConversationHeader
    ├── ConversationViewport
    │   ├── EmptyState
    │   ├── EntryList
    │   │   ├── UserMessage
    │   │   ├── AssistantMessage
    │   │   │   ├── TextPart
    │   │   │   ├── ReasoningSummary
    │   │   │   └── ToolActivity / ActivityGroup
    │   │   ├── PlanEntry
    │   │   ├── InteractionCard
    │   │   └── Notice
    │   ├── ActiveRun
    │   │   ├── StreamingDraft
    │   │   ├── LiveToolProgress
    │   │   └── PendingInteraction
    │   └── ScrollToBottomControl
    └── AgentComposer
        ├── ContextChips
        ├── Textarea
        ├── AttachmentControl
        ├── PermissionMenu
        ├── ModelLabel
        └── SendOrStop
```

避免 card-in-card。普通消息依靠留白、字体和细分隔线建立层次；只有工具、审批、
文件和错误等确实需要独立生命周期的内容使用卡片。

## 后端公开协议

### 类型化输入 Parts

普通消息和 steer 使用同一套输入：

```text
InputPart
├── text
├── attachment_ref
├── file_ref
├── directory_ref
├── workflow_ref
└── run_ref
```

`/context/search` 返回的 `input_part` 必须能原样通过命令提交，并在历史中转换为
可长期渲染的 typed part。不存在搜索结果只能展示、不能提交的死路。

服务端必须重新校验和规范化每个引用：attachment 属于当前 Session；file/directory
属于授权 Project 且通过路径穿越检查；workflow 在当前用户访问范围内；Run 与当前
Workspace/Project 匹配。前端提交的 label、路径细节和展示信息都不可信，由服务端按 ID
重新补全。ContextBuilder 必须把规范化引用真正提供给模型；directory 只提供目录说明和
按需读取能力，不自动把整个目录塞入上下文。

### 类型化历史 Parts

`MessagePayload` 只保留 `role + parts`，删除平行的 `content`、
`reasoning_summary`、`tool_calls`、`attachment_ids` 和 `artifact_ids`：

```text
MessagePart
├── text
├── reasoning_summary
├── tool_call
├── tool_result
├── attachment_ref
├── file_ref
├── directory_ref
├── workflow_ref
├── run_ref
├── artifact_ref
└── unknown
```

`HistoryEntry` 是封闭 union：`message | plan | interaction | notice`。`plan` 是顶层 entry，
不是 MessagePart；Interaction 完成后可作为永久 entry 留在时间线中。

工具调用至少包含：

```text
call_id, group_id, execution_mode, name, display_name, category, summary, arguments
```

同一 assistant entry 内的 tool call 使用该 entry ID 作为 `group_id`。不另造批次
实体，但让历史、实时进度和前端具有一个明确且稳定的聚合依据。

工具结果至少包含：

```text
call_id, status, summary, output, started_at, completed_at, error
```

`arguments` 和 `output` 外层必须类型化；其中的结构化值只允许尺寸受限的 `JsonValue`，
并由 Harness 清理敏感字段后公开。`output` 是 `text | json | content_parts` 封闭 union，
不得透传 provider 私有对象。产物统一使用独立 `artifact_ref` part，耗时由时间戳计算，
不双写 `duration_ms`。`unknown` 只允许 `original_type + display_text`，不能携带原始 JSON。

`category` 是公开展示语义，只允许稳定类别，例如 `read`、`command`、`edit`、
`write`、`interaction`。它不是 provider 工具名。

### 结构化 Plan

新增 `plan` entry，保存：

```text
plan_id, run_id, revision, title?, items[{id, text, status}], updated_at
```

Harness 提供一个轻量 `update_plan` 控制工具，只更新用户可见计划，不执行工作环境
副作用、不参与审批。该控制工具的调用和结果不再生成第二套公开 tool call/tool result；
它原子地追加新 revision 的 `plan` entry。它是满足明确产品需求的单一控制 primitive，
不恢复旧 Plan Mode、Todo 数据库或计划审批状态机。

计划更新追加为永久 entry，前端按 `plan_id + revision` 只投影当前 Run 的最新版，历史 Run
保留最终版本；旧 revision 仍可审计，但不在主时间线重复展示。

### 类型化 Interaction

```text
InteractionRequest
├── ask_user
├── approval
└── recovery
```

`approval` 明确携带工具、公开摘要、风险说明、输入预览和允许的响应；
`respond` 使用与 request kind 对应的封闭 response union，不再提交任意字典。

`assessment_fingerprint`、`cwd_identity`、`replay_policy`、checkpoint 和其他恢复校验
材料只保留在 Harness 私有状态，不进入 Snapshot、永久历史或前端。

### Session 公开视图

公开 Session 增加不含凭证的模型摘要：

```text
provider, model, display_name
```

可同时公开不含凭证的 `supports_vision / supports_reasoning / supports_tools`，用于
创建 Session 前的诚实能力提示；不得公开 base URL、凭证、target revision 或私有
模型快照。

新增：

```text
PATCH /agent/sessions/{session_id}
```

只允许更新：

- `title`；
- `permission_mode`；
- `workspace_access`（仅服务端策略允许时）；
- `status: active | archived`。

活动 Run 存在时修改 permission 返回 `409`。Session 模型继续在创建时冻结；
改变模型创建新 Session。

删除重复的 `GET /sessions/{id}`，只保留语义明确的
`GET /sessions/{id}/snapshot`。

### 四种用户命令

```text
message
steer
respond
cancel
```

`message` 取代公开的 `prompt + follow_up`：Harness 在同一个 Session mutation lock
内判断：

- 没有活动 Run：创建 Run；
- 有活动 Run：持久排队为下一条消息。

这避免前端根据可能过期的本地状态选择命令。

### Snapshot 和事件

保留六个事件族，但不把事件数量当目标：

```text
snapshot
run.updated
assistant.delta
tool.updated
interaction.requested
entry.committed
```

修正规则：

- `snapshot.snapshot` 必须非空；
- `entry.committed.entry` 必须非空；
- `run.updated` 携带完整公开 Run；Snapshot 同时携带 `runs[]`，避免刷新后丢失历史
  Run 的开始时间、结束时间、终态和耗时；
- `tool.updated` 携带完整 ToolProgressView；
- `interaction.requested` 携带完整 PendingInteractionView；
- `assistant.delta` 携带 `draft_id`、`part_id`、`part_type`、起止 offset 和 delta；
- `run.updated` 使用 Run 自身单调 `revision`；
- `tool.updated` 使用每个 `call_id` 自身单调 `revision`；
- interaction 使用稳定 ID 和自身 `revision`；
- `assistant.delta` 只使用 draft/part ID 和 offset，不用跨分片的全局 Run revision
  丢弃仍然有效的文字；
- entry 继续用 Session 内严格递增 sequence 去重。

`part_type` 至少覆盖 `text` 和用户可见的 `reasoning_summary`，从而让 Thinking 真正
流式更新；没有 provider summary 时不伪造内容。

每次 SSE 连接：先注册订阅，再取得 Snapshot，再发送队列事件。每个分片只与 Snapshot
中同一分片的基线比较，不使用一个全局 revision 排序不同种类的局部事件。

delta 归并规则固定为：

```text
event.end <= local.end         -> 重复，忽略
event.start == local.end       -> 追加
event.start > local.end        -> 出现缺口，立即重新请求 Snapshot
event.start < local.end < end  -> 协议异常，立即重新请求 Snapshot
```

不恢复 replay cursor。队列溢出或断线时关闭连接，客户端重连并以新 Snapshot
替换全部权威状态。

### 一次性 v2 数据迁移

新增一份 Alembic migration，不保留长期 v1/v2 双读：

1. `agent_runs` 增加非空 `revision INTEGER DEFAULT 0`，活动 tool/interaction 增加各自
   可恢复的 revision；
2. 把 message payload 的平行字段转换为 `parts[]` 并把 entry schema version 升为 2；
3. 把 tool role、`call_id` 和 `is_error` 转换为 `tool_result` part；
4. 把 reasoning、tool calls、attachment/artifact IDs 转换为对应 typed parts；
5. 把 Session/Run command queue 中的 `prompt`、`follow_up` 转换为 `message`；
6. 把活动 Run 的 draft 和 tool progress 转换为带稳定 ID、group/category 和 revision
   的新结构；
7. 从公开 interaction history 删除 fingerprint、cwd identity 等私有恢复材料，
   但在活动 checkpoint 中保留继续审批校验所需数据；
8. 把旧 `read_only` Session 映射为 `permission_mode=ask_changes` 和
   `workspace_access=read_only`，其他 Session 映射为 `workspace_access=read_write`；
9. 迁移活动 Run 时保留私有 checkpoint 的审批校验材料，并验证升级后可以继续恢复。

迁移后删除兼容解析分支。旧会话必须能直接产生 v2 Snapshot。

## 前端数据 Module

新建：

```text
frontend/lib/agent/
├── contracts.ts
├── client.ts
├── stream.ts
├── store.ts
├── selectors.ts
├── composer-document.ts
├── date-format.ts
└── session-preferences.ts
```

不增加 Zustand 或另一套全局状态依赖。使用纯 reducer/module 加薄 React hook。

Store 只支持：

```text
snapshot              -> 替换全部权威状态
run.updated           -> 按 Run revision 替换 Run
assistant.delta       -> 按 draft/part/offset 追加或忽略
tool.updated          -> 按 call_id + tool revision upsert
interaction.requested -> 按 interaction id + revision 替换
entry.committed       -> 按 id/sequence 追加并归并草稿/工具/交互
```

delta 出现缺口或重叠协议错误时，Store 不猜测缺失文本，通知 transport 重新获取 Snapshot。
Snapshot 替换时，若用户正在阅读历史，按可见 entry/part 锚点恢复滚动位置；仅在原本处于
跟随状态时滚动到底部。

高频文字 delta 在 `requestAnimationFrame` 内批量刷新；长历史 entry 使用稳定 key、
memoized part renderer 和 `content-visibility`，避免每个 chunk 重渲染整条时间线。

SSE transport 只负责连接、解析、重连和错误通知，不保存 replay cursor，不把事件
转换成另一套事件。

## 交互细节

### Streaming

- 正文和思考摘要使用不同稳定 part ID；
- Markdown 未闭合时仍能安全显示；
- streaming 时显示克制的运行状态，不使用永动装饰；
- Stop 发送 cancel 后进入 `cancelling`，保持 SSE 打开，直到收到权威 cancelled Run、
  notice 或新 Snapshot；
- entry committed 后不重复显示 draft。

### Thinking、Plan、Progress、Execution

- Thinking 只展示用户可见 reasoning summary，不展示或声称展示 raw chain of thought；
- Plan 使用结构化 checklist，显示 pending / in_progress / completed；
- Progress 由 Run phase、当前计划项和工具状态直接表达；
- Execution 由工具卡片和结果构成；
- 四者使用准确名称，不全部叫 Thinking。

### Tool Card 和 Activity Group

折叠态显示工具名称、公开摘要、状态、耗时和是否等待用户；展开态显示结构化参数、
命令、输出预览、错误和产物。未知工具使用 Generic Tool Card。

多个工具的 Activity Group：

- 标题使用真实 execution mode，例如“并行读取 4 个文件”或“依次执行 4 项操作”；
- running、failed、waiting approval 默认展开；全部成功完成后可以默认折叠；
- 展开后按 category 展示每个调用；
- 并行完成顺序可以变化，历史结果仍按模型调用顺序显示；
- 不用 Activity Group 隐藏失败、审批或需要用户接管的工具。

### Approval Card

- 显示 Agent 想做什么、影响范围、风险和关键参数；
- Approve / Reject 是明确按钮，提交后立即禁用，防止双击；
- 刷新后等待中的审批仍存在；
- 拒绝不是前端终止 Run，由 Harness 决定如何继续；
- Approval、Ask User、Recovery 共用 Interaction Card 外壳，但各自使用严格内容。

### Composer 权限菜单

使用 shadcn/Radix Popover 或 DropdownMenu，结构参考用户提供的 Codex 截图：

- 标题解释这是 Agent 操作确认方式；
- 三项各有名称、简短说明、图标和当前选择标记；
- composer 底部用紧凑状态显示当前模式；
- 新会话修改只改变草稿设置；
- 已有空闲 Session 修改调用 PATCH；
- 运行中禁用并解释原因；
- 选择 `full_access` 使用 warning 语义色，但不制造恐吓式弹窗。

### 基础体验

- 用户和助手消息提供复制按钮，成功静默确认，失败显示可恢复错误；
- Run 完成显示本地化结束时间和耗时；
- 用户接近底部时自动跟随；用户向上阅读时停止自动滚动；
- 有新内容且用户未在底部时显示 Scroll-to-bottom Control；
- 支持键盘发送、换行、停止、聚焦输入和新建会话；
- loading 使用与最终布局同形的 Skeleton；
- empty、error、disconnected、reconnecting 均有明确状态；
- 320 / 375 / 414 / 768 px 无横向滚动；
- 移动端 composer 使用 safe-area；权限菜单和右侧辅助面板降级为 Sheet；所有主要触控
  目标至少 44 px；
- 所有菜单、卡片、按钮和流式区域具有可访问名称、焦点顺序和状态通知。

## 保留、重写和删除

### 保留并按新类型复用

- 正式 `/agent` 路由和项目上下文；
- 应用导航、conversation sidebar 和 LiveDeck 外壳；
- 通用 Markdown / Shiki 渲染；
- 附件上传、预览和 Artifact 文件查看器；
- 模型连接对话框；
- 语音输入（只产生普通 text input part，不进入 Agent 协议）；
- shadcn UI primitives 和全局语义变量；
- 通用 API、SSE connection helper、clipboard 和响应式 hooks。

只有不依赖旧 Turn/Event/Action 类型的实现可以直接保留。

Session 创建后模型和 Workspace 固定；改变任一项都创建新 Session。删除旧执行位置
选择器、Token/压缩内部状态和环境浮层；这些 Harness 私有状态不进入工作台。

### 重写

- `frontend/hooks/use-agent-runtime.ts` -> 小型 `use-agent-session.ts`；
- `agent-workbench.tsx`；
- `agent-transcript.tsx`；
- `agent-composer.tsx`；
- permission control、approval/ask-user cards；
- sidebar conversation 类型和 session storage；
- command palette 中的 Agent session 行为；
- Agent settings 中仍引用旧 turn policy 的部分；
- demo runtime 与正式 Agent 页面之间的接线；
- 全部 Agent E2E 和旧协议 mock。

### 完全删除

- `frontend/lib/agent-core/`；
- `frontend/lib/agent-runtime/`；
- `frontend/components/bioinfoflow/agent-core/`；
- `frontend/components/bioinfoflow/agent-runtime/` 在通用实现迁出后整个删除；
- `frontend/lib/agent-runtime/public-events.ts`；
- replay cursor、event window 和旧 `/stream?after_seq=`；
- timeline / segments / activity projector；
- Action / Decision / Approval 旧领域类型和 pending-actions；
- 根据工具名、命令和 Run 状态猜测 UI 的代码；
- memory、agent tree、collaboration 和旧 todo 展示；
- `/agent/skills` 技能选择器；
- `/agent/fs/*` Agent 专属文件浏览协议；
- 独立 `/demo` Agent Core renderer 和 scenario event protocol；
- `frontend/hooks/use-agent-runtime.ts`；
- 所有针对已删除接口和投影逻辑的测试、mock 和 fixture。

Demo 若保留，只能使用正式 Agent workbench，注入确定性 test transport 或假模型。

会话列表只请求一次公开 Session summaries，再按 `project_id` 在产品层分组；不恢复
旧的 per-project Agent 接口。列表不暴露内部 `history_revision`。

以下跨目录调用者也必须同步改为新类型，不能让旧 import 藏在外围：

- `/agent` 和 `/agent/[sessionId]` 路由；
- sidebar conversation/project item 与 `use-sidebar-data`；
- command palette；
- Agent settings 中的旧 steer/queue/turn policy；
- demo runtime、scenario 和 `/demo` 页面；
- `messages/en.json`、`messages/zh-CN.json`；
- `app/globals.css` 中只服务旧 Agent halo/center-stage 的变量和样式。

删除 conversation 跨 project 拖拽；Session 的 project/workspace 绑定不通过前端拖拽
偷偷改变。删除全局“steer 或 queue”设置，普通发送由服务端自动决定，显式 steer
是 composer 中单独、清楚的动作。

## TDD 公开 Seams

本计划确认以下六个测试面；测试不穿透这些 interface 验证私有实现：

1. **HTTP / SSE seam**：Session、command、snapshot 和六类事件；
2. **Harness seam**：`dispatch + snapshot`，注入脚本化模型和真实临时 workspace；
3. **纯前端 Store seam**：`applyAgentEvent(state, event)`；
4. **React 产品 seam**：正式 conversation/composer，网络层 mock，按 role/text 查询；
5. **浏览器 seam**：真实前端、真实后端、临时 SQLite、本地 OpenAI-compatible 假模型。
6. **数据迁移 seam**：从真实 v1 fixture 执行 Alembic upgrade，再只通过 v2 Snapshot、
   command 和恢复行为验证结果。

测试只验证用户可观察行为；不 mock reducer 内部函数，不断言私有调用次数，不使用
CSS snapshot 代替交互验证。

## 垂直 Red -> Green 顺序

每个步骤只先写一个失败的行为测试，再做最小实现，通过后继续下一条：

1. v1 fixture -> Alembic upgrade -> 可恢复的 v2 Snapshot；
2. typed parts、typed interaction、完整事件和非空 payload；
3. `message / steer / respond / cancel` 和 Session PATCH；
4. Context ref 鉴权、规范化和真实模型上下文装配；
5. Snapshot 替换、entry 去重和分片 revision 归并；
6. streaming offset、重复/乱序/gap delta 和 committed reconciliation；
7. SSE 断线重连和完整 active Run 恢复；
8. text、reasoning summary、plan、unknown fallback、时间和复制；
9. 单工具卡片与具有真实 execution mode 的 Activity Group；
10. 副作用工具 -> approval -> respond -> continuation；
11. 三种 composer 权限模式、硬只读和运行中禁止切换；
12. Stop、scroll-to-bottom、loading/empty/error/mobile/a11y；
13. keyless Playwright 完整闭环。

已有 Workspace Runtime 串并行、沙箱和结果顺序测试继续作为事实来源，不复制一套
前端测试去验证 executor 私有实现。

## 确定性假模型

重写 `frontend/tests/e2e/support/mock-openai-server.mjs`，按第一条用户消息选择场景，
不使用跨测试全局状态：

- `stream answer`：reasoning summary chunks + text chunks；
- `show a plan`：调用 `update_plan` 后继续回答；
- `inspect in parallel`：一次响应产生多个可并行 read 调用，收到工具结果后总结；
- `edit in sequence`：一次响应产生存在顺序约束的调用，验证 serial/mixed 展示；
- `request approval`：产生危险 bash，批准或拒绝后继续；
- `ask a question`：调用 ask_user，收到答案后继续；
- `workflow run`：通过 bash 中的 `bif` 提交 demo workflow。

测试等待网络响应和可见状态，不使用任意 sleep；流式延迟只存在于假模型服务器。

## 建议提交切片

1. `docs: define complete agent harness frontend rearchitecture`
2. `refactor: harden agent public UI contracts`
3. `refactor: replace agent frontend state transport`
4. `feat: rebuild agent conversation workbench`
5. `test: cover agent browser workflows without provider keys`
6. `refactor: remove legacy agent frontend protocol`
7. `fix: address agent frontend review findings`

提交按可验证的纵向行为组织，不把所有测试写完后再一次性实现。

## 验证

### Backend

从 `backend/`：

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
```

### Frontend

从 `frontend/`：

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run test:coverage
rtk bun run build
rtk bunx playwright test tests/e2e/agent-streaming.spec.ts
rtk bunx playwright test tests/e2e/agent-tools.spec.ts
rtk bunx playwright test tests/e2e/agent-approval.spec.ts
```

Agent Playwright 测试最终在 Chromium、Firefox 和 WebKit 全部运行。

### 设计和可访问性 Review

- 使用最新 Vercel Web Interface Guidelines 检查正式 Agent 文件；
- 检查 320 / 375 / 414 / 768 / 1280 px；
- 检查键盘、焦点、ARIA、对比度、减少动态效果和无横向滚动；
- 按 Hallmark 的 Philosophy / Hierarchy / Execution / Specificity /
  Restraint / Variety 六项自评，任一低于 3 必须返工；
- 运行 Hallmark slop test，生产工作台不得引入展示型页面模式。

### Git

```bash
rtk git diff --check
rtk git status --short --ignored --untracked-files=all
```

## Review、PR 和合并

1. 以 `origin/main` merge-base 为 fixed point；
2. 使用 `code-review` 分别运行 Standards 和 Spec 两个独立 review；
3. 修复全部 confirmed findings，并重新运行受影响验证；
4. `rtk git fetch origin --prune`；
5. `rtk git rebase origin/main`；
6. 再运行核心后端、前端和 Agent Playwright gates；
7. 创建 Conventional Commit 标题的 PR；
8. 等待 CI、CodeQL、Vercel 和 required checks；
9. 发现 main 漂移时再次 rebase 并复验；
10. 检查通过后使用 PR 标题作为 squash merge commit 合并；
11. 合并后确认 `origin/main` 包含提交并检查工作树状态。

## 完成定义

1. `/agent` 可以使用真实新后端发送消息并收到 streaming 回复；
2. thinking summary、plan、progress 和 execution 使用不同、准确的 UI；
3. 单个、串行、并行和混合工具调用都能正确渲染、更新和恢复；
4. Approval、Ask User 和 Recovery 刷新后仍可继续；
5. composer 三种审批权限与 Harness 行为一致，硬只读不能被 UI 绕过；
6. 页面不解析 provider JSON，不推断工具类别或终态；
7. Snapshot 可以独立重建历史和当前 Run；
8. 断线、重复和乱序事件不会重复文本或倒退状态；
9. 复制、结束时间、Stop、Scroll-to-bottom 和移动端交互完整；
10. 删除全部旧 Agent Core、Turn/Event 投影、Action/Decision 和 replay cursor；
11. 正式页面和 Demo 不存在两套 renderer；
12. 后端、前端、coverage、build、dead-code、i18n 和 keyless E2E 全部通过；
13. 双轴 review 无未解决的严重或中等问题；
14. PR rebase 到最新 main，required checks 通过并完成 squash merge。

## 明确删除的复杂度

以下不是“以后再做”，而是根据第一性原理明确不进入设计：

- raw chain of thought 展示；
- provider 私有事件进入前端；
- replay cursor 和历史事件 ledger；
- Tool Batch / Activity 数据库；
- 前端 Harness Adapter Registry；
- 根据字符串猜工具、计划、进度和状态；
- 两套正式/演示 renderer；
- 为动画而动画；
- 新的全局状态框架；
- 为一个实现预先建设万能 Harness interface。

## 最终原则

重构后的前端只保留一条数据路径：

```text
Harness 公开事实
  -> Snapshot / semantic events
  -> 一个 Store
  -> typed entry / active Run renderer
  -> 用户看见并参与 Agent 工作
```

复杂度属于产生复杂度的地方。Harness 负责理解模型、工具和恢复；前端负责清楚、
可靠、舒适地展示工作并收集用户输入。
