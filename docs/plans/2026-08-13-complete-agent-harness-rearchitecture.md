# BioinfoFlow 完整 Agent Harness 重构计划

## 状态

本计划取代旧的 Durable Host / Agent Engine 讨论稿。旧稿保留作讨论记录，
不再作为实施依据。

这次不建设“可插拔 Agent 平台”，而是一次性把 BioinfoFlow 重构成一个完整、
单一的 Agent Harness。所有能力完成并通过验收后，正式 `/agent` 一次切换，
旧 Agent Core 随即删除，不长期双轨运行。

## 目标

> BioinfoFlow 只有一个完整 Agent。它自己组织上下文、调用模型、调用工具、
> 询问用户、继续思考、压缩、重试、取消和恢复。BioinfoFlow 产品只提供身份、
> 工作环境、生信能力、历史存储和网页界面。

完整 Harness 必须在本次重构中同时具备：

- 一份永久会话历史；
- 一条模型—工具—模型循环；
- 上下文组装和压缩；
- 模型流式调用和多供应商支持；
- 工具校验、确认、串并行、执行和结果回填；
- 运行中追加指令、后续消息和取消；
- 模型错误重试、预算和无进展保护；
- 进程重启后的同版本恢复；
- 历史重新打开和完整渲染。

## 第一性原理

### Agent 的最小闭环不可拆

```text
用户输入
  -> 从历史组装上下文
  -> 调用模型
  -> 模型回答或提出工具调用
  -> Harness 校验、确认并执行工具
  -> 工具结果写回历史
  -> 再次调用模型
  -> 没有工具调用和待处理输入时结束
```

工具调用、审批、执行、结果回填和继续调用模型属于同一闭环。把其中任何一步
交给另一个平台状态机，都会重新产生两套 Agent。

### 永久历史和恢复状态分开

- 永久历史保存“已经发生了什么”，长期可读、可搜索、可渲染。
- 私有恢复状态保存“未完成工作做到哪里”，只供当前 Harness 版本恢复。

删除恢复状态后，旧对话仍必须完整可读。压缩只改变发给模型的上下文，
不删除原始历史。

### 软确认和硬安全分开

- Harness 决定何时询问用户，以及拒绝后如何继续。
- 工作环境强制文件、进程、容器、挂载和网络边界。
- BioinfoFlow 后端对项目、运行、连接和数据重新鉴权。

不再建设一套与 Harness 并行的通用审批系统。真正不可绕过的规则必须存在于
操作系统沙箱、短期凭证或服务端权限检查中。

### 完整不等于工具繁多

完整指闭环完整，不是预装无限工具。一个 `bash` 可以清晰完成的能力，不再拆成
许多模型工具。

### 不为假想替换建设接口

本次只有一个生产 Harness，因此不定义 Agent Engine、Harness Adapter、
跨 Harness checkpoint 或运行中迁移协议。模型供应商和本地/远程工作环境确实有
多个实现，只在这两个真实变化点保留内部 seam。

## 参考实现

以 Pi 已发布的 AgentSession 和 agent loop 为主要模仿对象，不抽取 Pi、Hermes、
Codex、Claude 的最大公约数。

采用 Pi 的核心做法：

- 只有一条模型—工具循环；
- 工具调用和工具结果属于正式会话历史；
- Session 负责模型、上下文、工具、压缩和运行控制；
- 产品通过命令和事件接入，不接管循环；
- 核心工具很少，开放能力交给命令行和扩展环境。

Codex、Claude Code、Hermes 和 OpenAI 官方工具文档只用于校验工具、安全和
用户交互的取舍。

研究依据：

- `docs/research/2026-08-13-modern-agent-harness-ownership.md`
- `docs/research/2026-08-13-minimal-complete-agent-harness.md`
- [Pi Agent Loop](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent-loop.ts)
- [Pi Coding Agent](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/README.md)
- [Claude Code Tools](https://code.claude.com/docs/en/tools-reference)
- [OpenAI Tools](https://developers.openai.com/api/docs/guides/tools)

## 目标结构

```text
Browser / bif agent
        |
        | prompt / steer / answer / cancel / snapshot / events
        v
+---------------- BioinfoFlow Agent Harness ----------------+
| Session history -> Context -> Model -> Tools -> Results    |
|        ^             |          |         |        |       |
|        +----- Compression / Retry / Recovery <-----+       |
+----------------------+----------------------+-------+
                       |                      |
                       v                      v
                Model Runtime          Workspace Runtime
             OpenAI / Anthropic       local / remote SSH
                                              |
                                     five tools + bif CLI
                                              |
                                   authenticated BioinfoFlow API
```

对 HTTP、CLI 和前端，Harness 是一个深 module，只暴露：

```python
class AgentHarness:
    async def open_session(request) -> SessionSnapshot: ...
    async def dispatch(session_id, command) -> None: ...
    async def snapshot(session_id) -> SessionSnapshot: ...
    async def events(session_id) -> AsyncIterator[AgentEvent]: ...
```

`command` 只有五种：

- `prompt`：开始一次新 Run；
- `steer`：在当前 Run 的下一个安全点加入指令；
- `follow_up`：当前 Run 结束后自动开始新 Run；
- `respond`：回答问题、确认或恢复选择；
- `cancel`：取消当前 Run。

不要为只有一个生产实现的 Harness 创建 Protocol、Registry 或 Adapter 层。测试直接
使用真实 Harness，注入内存存储、假模型和假工作环境。

建议新包：

```text
backend/app/services/agent_harness/
├── harness.py       # 唯一外部 interface
├── loop.py          # 唯一模型—工具循环
├── history.py       # 永久历史和当前上下文视图
├── context.py       # 提示词、项目说明、技能和附件
├── compression.py
├── recovery.py
├── events.py
├── workspace.py     # local 与 remote 两个真实 adapter
└── tools/
    ├── executor.py
    ├── read.py
    ├── bash.py
    ├── edit.py
    ├── write.py
    └── ask_user.py
```

现有 `backend/app/services/model_runtime/` 继续负责供应商协议和 I/O；循环、重试、
压缩与终止策略属于 Harness。

## 唯一运行循环

一次用户 `prompt` 对应一个 Run。同一 Session 同时最多一个活动 Run。

1. 创建 Run，把用户消息追加到永久历史。
2. 获取短租约，防止两个 worker 同时推进。
3. 从提示词快照、压缩摘要、最近历史、项目说明和附件构造模型输入。
4. 流式调用模型，当前草稿写入 Run 快照。
5. 模型结束后，把完整助手消息追加到永久历史。
6. 没有工具调用则完成 Run。
7. 有工具调用则先保存最终调用，再由 Harness 确认和执行。
8. 工具结果按模型原始调用顺序追加到永久历史。
9. 返回第 3 步，直到没有工具调用和待处理输入。

`steer` 存入当前 Run 的持久队列，在模型请求或工具批次结束后的安全点加入历史。
`follow_up` 存入 Session 队列，当前 Run 结束后创建新 Run。所有命令使用命令 ID
去重。

同一个取消信号贯穿模型流、工具、命令进程组、SSH 和用户等待。取消后保存已经
完成的历史，为未完成工具写入 cancelled/interrupted 结果，然后结束 Run。

## 最小工具面

模型默认只看见：

```text
read
bash
edit
write
ask_user
```

不再默认暴露 `grep`、`find`、`ls`、`web.search`、`todo_write`、计划模式、
协作工具、memory 工具或几十个 BioinfoFlow 函数工具。

### `read`

- 文本按行分页，返回继续读取位置；
- 图片作为多模态内容；
- 大文件明确截断；
- 路径经过 Workspace Runtime 校验；
- 二进制和领域大文件提示使用合适命令行程序。

### `bash`

统一承担：

- `rg`、`find`、`ls`、`jq`、`sed`；
- Git、测试、构建和格式化；
- Python、R、Nextflow、MiniWDL；
- `curl` 等公开网络客户端；
- `bif --output json`。

必须实现 OS 沙箱、网络策略、工作目录、超时、进程组取消、累积输出限制、超大
输出 Artifact、命令风险确认，并确保长期凭证不进入子进程。

### `edit`

- 精确旧文本匹配，默认要求唯一；
- 修改前重新读取，防止覆盖新变化；
- 返回标准 diff；
- 同一路径修改严格串行。

### `write`

- 创建或完整覆盖文件；
- 创建允许范围内的父目录；
- 覆盖时返回 diff；
- 同路径写入串行；
- 重复写入相同内容视为幂等成功。

### `ask_user`

普通澄清、危险操作确认和崩溃恢复选择共用一条用户交互通道。无需 Ask User、
Approval、Decision Request、Plan Exit 四套状态机。

### 串并行

- `read` 默认并行；
- `bash` 默认串行，只有能证明互不影响的只读调用才并行；
- `edit/write` 不同路径可并行，同一路径串行；
- `ask_user` 始终串行并暂停 Run；
- 结果始终按模型调用顺序写回历史。

这些规则是 executor 的内部实现，不保存 Tool Batch 表。

## BioinfoFlow 能力统一通过 `bif`

模型不再面对 `projects.*`、`runs.*`、`workflows.*`、`remote.*` 等大量工具。
Harness 给 `bash` 中的 `bif` 注入：

```text
BIOFLOW_API_URL
BIOFLOW_PROJECT
BIOFLOW_OUTPUT=json
BIOFLOW_AGENT_TOKEN=<short-lived scoped token>
```

短期 Agent Token 必须：

- 绑定 user、workspace、session 和 run；
- 只保存哈希，明文只存在于当前工具进程；
- 短期有效并按需轮换；
- Run 结束、取消或 Session 删除后失效；
- 不进入模型上下文、工具结果、日志、Artifact 或永久历史。

API 每次调用仍按真实用户和当前角色重新鉴权。为 `bif` 补齐 Agent 必需但 CLI 尚未
覆盖的连接查询、受保护文件访问和远程执行等命令；优先增加 CLI 子命令，不增加
模型工具。

查询类 `bif` 命令自动执行；创建、提交、修改遵循 Session 权限模式；删除、清理、
覆盖远程状态等危险操作要求确认。

Session 权限模式只保留三种：

- `read_only`；
- `ask_dangerous`；
- `full_access`。

`full_access` 只减少交互确认，不能突破沙箱、网络和服务端权限。

## 历史、上下文和压缩

永久历史只使用一个追加式 `agent_entries` 表。条目是带版本的封闭联合：

- `message`：user、assistant、tool；
- `interaction_request`；
- `interaction_response`；
- `compaction`；
- `notice`：取消、崩溃和恢复等用户可见事实。

助手消息可包含正文、可选思考摘要、工具调用和 Artifact 引用；工具结果使用
`call_id` 关联。旧对话渲染只读取 entries，不读取 checkpoint。

Session 创建时保存稳定提示词快照：

- Agent 核心行为；
- 当前 workspace、project 和工作环境；
- 五个工具说明；
- 从当前目录向上发现的 `AGENTS.md` 或 `CLAUDE.md`；
- 可用技能的名称、描述和文件路径。

技能不需要 `skills.load` 工具。需要时直接用 `read` 打开 `SKILL.md` 及其引用文件。

上下文接近模型上限时：

1. 总结旧区间的目标、已完成工作、关键事实、文件、命令、错误、用户决定和未完成项；
2. 把摘要追加为 `compaction` entry；
3. 后续请求使用摘要加最近历史；
4. 原始历史永不删除。

上下文溢出时压缩并重试一次，禁止静默截断工具结果或用户决定。

删除独立 Agent Memory 数据库。长期知识应进入项目文档、技能或用户明确管理的资料，
不由 Harness 自动制造第二份记忆真相。

## 最小持久化模型

### `agent_sessions`

保存用户、工作区、项目、标题、模型、工作环境、权限模式、提示词快照和历史 revision。

### `agent_runs`

保存一次连续工作的状态：

- `queued / running / waiting_user / completed / failed / cancelled`；
- 当前阶段 `model / tools / interaction`；
- 模型快照、短租约、持久命令队列；
- 当前草稿和工具进度；
- 私有 checkpoint；
- 重试、用量、终止原因和错误；
- Agent Token 哈希与过期时间。

租约只是防止重复 worker 推进的内部实现，不进入历史或前端领域模型。

### `agent_entries`

保存 Session、Run、严格递增序号、条目类型、schema version、typed payload 和时间。
它是渲染和下一次上下文组装的唯一历史事实来源。

### `agent_attachments` 与 `agent_artifacts`

保留附件、多模态内容、大型命令输出和用户可下载结果。Artifact 是文件或结果，
不是 Agent 状态。

### 一次性迁移

把现有已提交 user/assistant/tool 历史转为 entries，保留附件和 Artifact。未完成的旧
Run 追加 `interrupted_by_upgrade` notice，不重放旧副作用。

迁移后删除旧 `agent_turns`、`agent_actions`、`agent_tool_call_batches`、
`agent_events`、`agent_memories` 以及通用 approval/decision 数据。不存在长期双读、
双写或兼容分支。

## 同版本恢复

checkpoint 只保存未完成 Run 的最小私有状态：当前阶段、已消费历史 revision、
输入队列、模型 continuation、未提交草稿、未完成工具、等待交互、压缩位置和预算。

在以下位置持久化：

- 调用模型前；
- 完整助手消息提交后；
- 工具执行前；
- 每个工具结果提交后；
- 等待用户前；
- 压缩提交后；
- Run 终止前。

每个工具声明重放策略：

- `safe`：可自动重试，例如 `read`；
- `verify`：先检查目标状态，再决定是否重试，例如 `edit/write`；
- `never`：不能自动重放，例如任意 `bash` 副作用。

如果进程在 `bash` 开始后、结果保存前退出，恢复时不自动执行第二次。Harness 写入
用户可见 notice，通过统一用户交互让用户选择“检查现状后继续”“明确重试”或“取消”。

Run 终止后删除无用 continuation 和临时草稿，只保留永久历史、用量和终止信息。

## 模型重试和终止

复用现有 ModelGateway，但 Harness 决定何时调用、何时重试、何时压缩和何时结束。

- 连接失败、限流和无语义输出的临时错误指数退避重试；
- 已产生语义输出后不静默重新请求；
- 上下文溢出先压缩再重试一次；
- 鉴权、无权限和无效请求立即失败；
- 不做隐藏的跨模型自动 fallback；
- 使用最大模型迭代、最长运行时间、token 和工具输出预算；
- 连续重复同一工具调用和结果时纠偏一次，再重复则停止。

## API、事件和前端

每次 SSE 连接先发送权威 snapshot，再发送当前连接期间的增量；断线后重新取 snapshot，
不再维护历史事件 replay cursor。

Snapshot 包含 Session、永久 entries、当前 Run、当前助手草稿、工具进度和等待中的
用户交互。

事件只保留：

```text
snapshot
run.updated
assistant.delta
tool.updated
interaction.requested
entry.committed
```

前端不再：

- 把公开事件还原成内部事件；
- 关联 Tool Call、Action 和 Artifact 三套 ID；
- 根据工具名或命令正则猜 Activity；
- 根据 Run 状态推断工具状态；
- 理解 lease、checkpoint、compression state 或 continuation。

新的前端 store 只应用 snapshot 和六种事件，React 直接渲染 entries 和当前 Run。
删除旧 `/demo` Agent Core renderer，demo 若保留则使用正式 Agent 页面。

## 删除清单

以下内容直接删除，不作为未来承诺：

- Durable Host / Agent Engine 双层架构和 R1–R4；
- Harness Adapter Registry 和跨 Harness 迁移；
- 平台 Tool Call / Tool Action 状态机；
- Approval / Decision / Action Audit 状态机；
- Tool Batch 表和 batch coordinator；
- event ledger、replay cursor 和 activity projector；
- 通用 Agent plugin framework；
- 内建计划模式、TODO、Agent Memory 和多 Agent collaboration；
- 默认网页搜索、浏览器和每个产品动作一个工具。

当前代码中保留并迁移的部分：

- `model_runtime` 供应商支持；
- 模型 profile、凭证和访问控制；
- OS sandbox、路径边界和命令风险经验；
- 现有 `bash/read/edit/write/ask_user` 的可复用实现；
- Attachment、Artifact 和 Skills 文件发现；
- BioinfoFlow 业务服务、HTTP API 和 `bif` CLI。

切换后删除旧 `AgentLoopController`、runtime/service/runner 运行路径、Action/Batch/Event/
Memory repository、旧 executor/dispatcher/middleware、几十个 platform model tools、
collaboration、plan/todo，以及前端 timeline/activity/event 解释代码。

禁止在旧 AgentLoopController 外再包一层新 façade。能复用的实现先移入新 Harness 并
通过新 interface 测试，然后删除旧位置。

## 一次性实施顺序

这些步骤用于控制开发风险，不代表分批发布。

1. 定义 `AgentCommand`、Snapshot、六种事件、entries union 和五工具契约；先写
   Harness interface 级测试与确定性假模型。
2. 建立 Session、Run、Entry 存储、短租约、命令去重和旧历史迁移。
3. 实现唯一模型—工具循环、流式输出、steer、follow-up、cancel、预算和无进展保护。
4. 重写五个工具，完成沙箱、风险确认、串并行和恢复语义。
5. 实现短期 Agent Token，扩展 `bif` 和 API Bearer 认证，补齐必要 CLI 命令。
6. 完成提示词、项目说明、Skills、压缩和模型/工具/交互各阶段重启恢复。
7. 替换 agent API、`bif agent`、SSE 和正式前端；统一所有确认到 interaction response。
8. 删除旧代码、旧表、旧事件翻译和旧 renderer，运行全量验证后切换 `/agent`。

## 关键验收

### 核心闭环

- 纯文本、多轮工具、并行 read、同路径写入串行；
- malformed 参数和 bash 非零退出不会使 Harness 崩溃；
- 工具结果顺序稳定；
- steer、follow-up 和取消正确；
- 重复无进展调用会终止。

### 用户交互与恢复

- 普通提问、危险命令确认、拒绝后继续；
- 等待用户时重启后仍可回答；
- 模型流和 bash 运行中可取消；
- 在模型前后、工具前后、压缩和等待阶段 kill/restart；
- read 自动恢复，edit/write 先验证，未知 bash 副作用绝不静默重放；
- checkpoint 损坏时能从永久历史保守恢复。

### 历史与压缩

- 旧 committed conversation 迁移后可读；
- 工具调用、结果和用户确认完整渲染；
- 压缩后继续完成任务，原始历史仍完整；
- 删除 continuation 后旧对话仍能打开；
- 大输出进入 Artifact，模型得到有用摘要。

### 权限

- 三种权限模式正确；
- `full_access` 仍不能突破沙箱和服务端鉴权；
- Agent Token 过期、撤销和跨 Run 重放失败；
- team mode 普通成员不能借 Agent 获得管理员能力；
- token 不进入历史、输出、日志或 Artifact；
- local 与 remote workspace 通过相同五工具测试。

### 前端

- 首帧 snapshot、流式 delta、刷新重连和 pending interaction 正确；
- 前端不推断工具终态；
- 历史打开不依赖旧 Harness 进程。

### 工程命令

从 `backend/`：

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
```

从 `frontend/`：

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

从仓库根目录：

```bash
rtk docker compose up -d --build
rtk docker compose logs backend frontend
rtk git diff --check
```

使用一个真实 OpenAI 模型和一个真实 Anthropic 模型完成：读取项目、修改文件、
执行测试、通过 `bif` 提交 demo workflow、等待确认、重启后继续和重新打开历史。

## 完成定义

1. 用户输入到最终回答只有一条模型—工具循环。
2. 上下文、模型、工具、确认、压缩、重试、取消和恢复全部属于新 Harness。
3. 模型默认只暴露 `read/bash/edit/write/ask_user`。
4. BioinfoFlow 产品能力统一通过带短期身份的 `bif` 进入。
5. 永久历史可独立渲染，checkpoint 删除后历史仍完整。
6. 同版本 Harness 能从模型、工具和用户等待阶段的进程退出中恢复。
7. 未知 bash 副作用绝不自动重放。
8. 前端只渲染 snapshot、entries 和当前 Run。
9. 旧 Agent Core 代码、表、事件翻译和 renderer 已删除。
10. 不存在 Host/Engine、Action Runtime、Tool Batch 或跨 Harness 热切换抽象。
11. 旧已提交历史、附件和 Artifact 已完成一次性迁移。
12. 后端、前端、迁移、Docker 和真实模型冒烟全部通过。

## 最小术语

| 中文 | English | 定义 |
| --- | --- | --- |
| Agent 运行器 | Agent Harness | 完整负责模型、工具、上下文、确认、压缩、重试和恢复。 |
| 会话 | Session | 用户长期保存的一段对话和工作范围。 |
| 一次运行 | Run | 从一次 prompt 到完成、失败或取消的连续工作。 |
| 历史条目 | History Entry | 永久追加、可独立渲染的消息、工具结果或交互。 |
| 工具调用 | Tool Call | 模型请求执行某个工具及其参数。 |
| 工具结果 | Tool Result | 工具执行后写回历史并交给模型的结果。 |
| 用户交互 | User Interaction | Agent 暂停并等待提问、确认或恢复选择。 |
| 上下文 | Context | 某次模型调用实际收到的提示词、摘要、最近历史和工具。 |
| 上下文压缩 | Compaction | 保留原历史，用摘要替换旧内容进入当前上下文。 |
| 恢复状态 | Checkpoint | 当前 Harness 版本继续未完成 Run 的私有状态。 |
| 工作环境 | Workspace Runtime | 执行文件和命令并强制文件、网络、进程和凭证边界。 |

`Turn`、`Action`、`Decision`、`Ledger`、`Replay Cursor`、`Engine`、
`Canonical Conversation` 和 `Strangler` 不再作为产品领域语义。租约或内部 seam 若仍
存在，只是实现细节。

## 最终原则

这次重构只留下三条主线：

1. 一条 Agent 循环；
2. 一份永久历史；
3. 五个核心工具，其中开放世界能力主要通过 `bash` 和带身份的 `bif` 完成。

其他复杂度只有在真实语义不同、且无法由这三条主线覆盖时才允许存在。
