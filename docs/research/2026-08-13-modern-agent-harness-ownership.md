# 现代 Agent Harness 职责调研

日期：2026-08-13

调研对象与固定版本：

- Pi `46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106`
- Hermes Agent `7fa084f58ecf496c2d3b7a8f8d7afd0843103895`
- Goose `11deb564d09db782a17878af7cfafd299d9fa461`
- OpenCode `cc4b45612974f735ddec46009ede07729511fba4`

## 结论

用户的直觉基本正确：一个完整的 agent 应当自己负责“思考、决定调用什么工具、执行工具、询问批准、把结果交还模型、继续思考”这一整套循环。BioinfoFlow 不应把其中一段切走，再建设第二套工具调用、审批和恢复状态机。

更简单的目标图景是：Pi、Hermes、Goose、OpenCode，甚至 Codex，仍然是完整的 agent；BioinfoFlow 给它们提供生信工具、数据、算力、身份、隔离环境和产品界面。换一个 agent，类似换一台发动机，而不是重造半台发动机再要求所有厂商适配它。

四个项目的已发布实现都支持这个判断：工具循环归 agent runtime 所有，产品界面通过事件、RPC 或 ACP 与其连接。没有证据表明“在一轮运行中任意热换 harness”是成熟共识或必要能力。

## 用大白话说重构前后

重构前的讨论稿倾向于让平台掌握很多 agent 内部步骤：平台记录它作了什么决定、准备调用什么工具、工具是否获批、执行到哪里，并希望任何 agent 都按平台的步骤运行。这样做的代价是，平台逐渐变成一个自制 agent；接入 Pi 或 Hermes 时，必须拆开对方原本完整的能力。

建议的重构后形态是：

- agent 仍然完整工作，BioinfoFlow 不插手它内部每一步怎么想、怎么循环。
- BioinfoFlow 把“运行工作流、访问样本、读取结果、管理文件”等生信能力提供成 agent 能认识的工具。
- agent 认为某个操作需要批准时，通过自己的标准机制向 BioinfoFlow 页面发出请求；页面只负责展示并把用户答案送回去。
- BioinfoFlow 用容器、挂载、网络和凭证控制真正不可越过的安全边界。
- 页面保存或同步完整对话，因此即使以后不再使用原 agent，旧对话仍然能查看。
- 换 agent 发生在新任务、新对话，或一轮工作结束之后；首版不承诺执行到一半无损换人继续。

这不是“平台什么都不管”，而是让每一层只管自己真正擅长且能强制保证的事情。

## 最小职责边界

| 事项 | 建议所有者 | 原因 |
| --- | --- | --- |
| 选择模型、组织上下文、连续思考 | Agent | 这是 agent 行为的核心，不同产品差异很大 |
| 生成工具调用 | Agent | 工具调用由模型输出，并由 agent 循环消费 |
| 工具执行顺序、并发、重试、结果回填 | Agent | 必须与模型循环、上下文和恢复语义保持一致 |
| 工具权限判断和交互式批准 | Agent | Pi、Hermes、Goose、OpenCode 都将它放在 agent 执行管线内 |
| 生信工具的具体实现 | BioinfoFlow | 工作流、数据、文件、容器和计算资源属于领域平台 |
| 用户、团队、项目、工作区 | BioinfoFlow | 属于产品和业务边界 |
| 容器、文件挂载、网络、凭证范围 | BioinfoFlow | 这是可强制执行、不可绕过的硬安全边界 |
| 对话和事件的页面展示 | BioinfoFlow | 平台消费 agent 输出，不反向拥有 agent 状态机 |
| 模型供应商私有续接信息 | Agent 保存，平台可附带存储 | 是优化信息，不应成为旧对话渲染前提 |
| 外部审计 | BioinfoFlow | 可观察并保存事实，但不复制一套执行状态机 |

如果法规要求某条规则绝不能绕过，应把它放在领域工具、凭证代理、容器或操作系统边界，而不是再增加一个与 agent 审批并行、可能相互矛盾的平台审批器。

## Pi

### 已发布行为

Pi 的已发布 agent loop 在 assistant 返回工具调用后，直接查找工具、执行工具并把结果放回上下文，然后继续下一次模型调用；调用方订阅流式事件即可。见 [`agent-loop.ts` 第 155-274 行](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent-loop.ts#L155-L274)。

Pi Coding Agent 的会话 JSONL 直接保存用户消息、助手文本、思考内容、工具调用、工具结果和自定义展示消息，足以独立重建和渲染历史。见 [`session-format.md` 第 1-41 行](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/session-format.md#L1-L41)及[消息结构](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/session-format.md#L43-L171)。

Pi 已提供适合产品平台接入的 RPC 模式：外部程序发送命令、接收 agent 事件，并可提示、转向、跟进和取消，而无需接管内部工具循环。见 [`rpc.md` 第 1-26 行](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/rpc.md#L1-L26)和[运行中输入语义](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/rpc.md#L41-L83)。

Pi 没有声称进程内权限检查是可靠沙箱。它明确说明工具以启动用户权限运行，真正隔离应来自容器、虚拟机或操作系统。见 [`security.md` 第 31-53 行](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/security.md#L31-L53)。这正好支持 BioinfoFlow 保留部署级硬边界，而不接管工具循环。

### 设计方向，不是已发布能力

Pi 新的 durable `AgentHarness` 类型表达了更强的会话、操作恢复、工具副作用记录和 hook 设计，但当前 `events.on()`、`hooks.on()`、`prompt()`、`resume()` 等核心入口仍会抛出 `HarnessNotImplemented`。见 [`agent-harness.ts` 第 219-258 行](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/harness/agent-harness.ts#L219-L258)。因此它可作为设计参考，不能作为 BioinfoFlow 首版已经可依赖的恢复协议。

### 对 BioinfoFlow 的启示

优先接 Pi 已发布的 `AgentSession` 或 RPC 事件面；不要为了等待或复刻未完成的 durable harness，而先制造一套平台级 Turn、Action、Decision 状态机。

## Hermes Agent

### 已发布行为

Hermes 的 `run_conversation()` 驱动完整对话，并在模型给出工具调用后调用自身 `_execute_tool_calls()`，继续模型循环。见 [`conversation_loop.py` 第 1428 行起](https://github.com/NousResearch/hermes-agent/blob/7fa084f58ecf496c2d3b7a8f8d7afd0843103895/agent/conversation_loop.py#L1428-L1508)和[工具执行入口](https://github.com/NousResearch/hermes-agent/blob/7fa084f58ecf496c2d3b7a8f8d7afd0843103895/agent/conversation_loop.py#L6750-L6790)。

危险命令识别、会话批准状态、交互提示、智能批准和永久白名单明确由 Hermes 的批准模块统一负责。见 [`approval.py` 第 1-9 行](https://github.com/NousResearch/hermes-agent/blob/7fa084f58ecf496c2d3b7a8f8d7afd0843103895/tools/approval.py#L1-L9)。CLI、Gateway 或 Desktop 可以提供回调和界面，但不重新判定批准规则。

Hermes 的 `SessionDB` 是 SQLite 会话库，保存完整消息历史和模型配置，供 CLI 与 Gateway 共用。见 [`hermes_state.py` 第 1-15 行](https://github.com/NousResearch/hermes-agent/blob/7fa084f58ecf496c2d3b7a8f8d7afd0843103895/hermes_state.py#L1-L15)和[`SessionDB` 定义](https://github.com/NousResearch/hermes-agent/blob/7fa084f58ecf496c2d3b7a8f8d7afd0843103895/hermes_state.py#L2679-L2685)。

### 成熟度限定

Hermes 的工作区 checkpoint 主要用于文件快照与回滚，不能等同于“换任意 harness 后继续一轮模型—工具循环”。历史可读与运行中精确续接是两个不同目标。

### 对 BioinfoFlow 的启示

Gateway/Desktop 的做法更接近正确平台关系：宿主负责入口和展示，Hermes 保持完整 runtime。BioinfoFlow 应通过 Hermes 的事件和回调接入批准界面，而不是把批准逻辑搬出来。

## Goose

### 已发布行为

Goose 的 `AgentConfig` 直接持有会话管理器和权限管理器；`Agent` 自身持有扩展工具、确认路由、工具结果通道和状态机。见 [`agent.rs` 第 188-221 行](https://github.com/block/goose/blob/11deb564d09db782a17878af7cfafd299d9fa461/crates/goose/src/agents/agent.rs#L188-L221)及[`Agent` 字段](https://github.com/block/goose/blob/11deb564d09db782a17878af7cfafd299d9fa461/crates/goose/src/agents/agent.rs#L252-L278)。

工具批准是 Goose 状态机的一步：它从已保存对话恢复批准状态，检查待处理工具并产生需要用户操作的消息。见 [`ops_tool_approval.rs` 第 43-125 行](https://github.com/block/goose/blob/11deb564d09db782a17878af7cfafd299d9fa461/crates/goose/src/agents/state_machine/ops_tool_approval.rs#L43-L125)。工具执行同样是 agent 状态机中的操作，并通过扩展管理器获得和调用工具。见 [`ops_toolcalling.rs` 第 576-604 行](https://github.com/block/goose/blob/11deb564d09db782a17878af7cfafd299d9fa461/crates/goose/src/agents/state_machine/ops_toolcalling.rs#L576-L604)。

Goose 会把批准请求和回复作为对话内容保存，所以界面只需展示并返回用户选择。它也提供 ACP 接入面，适合 IDE 或产品宿主消费 agent 能力，而不是拆分 agent 内部循环。

### 成熟度限定

Goose 可保存供应商原生 session id，并在后续调用尝试 `provider.resume()`。这是同一供应商的快速续接优化，不是跨 harness 通用 checkpoint；对某些由供应商管理上下文的实现，更换模型或供应商本来就会受限。见 [`agent.rs` 的 provider resume](https://github.com/block/goose/blob/11deb564d09db782a17878af7cfafd299d9fa461/crates/goose/src/agents/agent.rs#L2160-L2200)。

### 对 BioinfoFlow 的启示

持久化批准事实很有价值，但状态仍应由 Goose 自己解释。BioinfoFlow 可镜像这些消息用于展示和审计，不应再推导另一份“可执行/不可执行”真相。

## OpenCode

### 已发布行为

OpenCode 的 `SessionPrompt.runLoop()` 从持久化历史开始，选择模型与 agent，构造工具，调用模型，处理工具结果并继续循环。见 [`prompt.ts` 第 1081-1139 行](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/packages/opencode/src/session/prompt.ts#L1081-L1139)和[工具解析](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/packages/opencode/src/session/prompt.ts#L1221-L1240)。

权限服务在 OpenCode 进程内评估允许、拒绝或询问；需要询问时发布事件并等待界面回复。见 [`permission/index.ts` 第 67-106 行](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/packages/opencode/src/permission/index.ts#L67-L106)。界面是投影和交互端，不是权限规则的另一个所有者。

OpenCode 对内部两种模型运行路径的说明也明确：无论默认 AI SDK 还是实验 native runtime，工具执行都归 OpenCode 所有，变化的只是请求转换和传输。见 [`session/llm/AGENTS.md` 第 25-36 行](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/packages/opencode/src/session/llm/AGENTS.md#L25-L36)和[所有权结论](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/packages/opencode/src/session/llm/AGENTS.md#L83-L90)。

### 实验和未完成部分

Native LLM 路径必须通过实验开关启用，不能当作默认已发布架构。更深的 V2 崩溃后自动续接也明确被推迟；现阶段遗留的运行中工具会被标为中断，副作用不会被静默重放。见 [`specs/v2/session.md` 第 153-173 行](https://github.com/anomalyco/opencode/blob/cc4b45612974f735ddec46009ede07729511fba4/specs/v2/session.md#L153-L173)。

### 对 BioinfoFlow 的启示

“先保存可见事实，重启后明确标记中断，不自动重放不确定副作用”比首版建设跨 harness 精确恢复更简单、更可靠。

## 历史数据库与私有 checkpoint

“把 checkpoint 写进历史数据库”这个方向需要拆成两层：

第一层是必须长期保留、可以独立渲染的历史：用户消息、助手消息、工具调用、工具结果、批准请求、用户答复、错误、附件、用量和展示元数据。它应进入数据库或原始会话存储，并有版本化格式。更换 harness 后，旧对话至少仍可只读查看，也可通过显式转换导入新 harness。

第二层是可选的私有续接信息：供应商 session id、加密思考数据、缓存句柄、原生 continuation token 等。它可以作为同一历史记录的私有附属字段保存，但不能成为显示旧对话的必要条件，也不应假设另一个 harness 能理解它。

因此最小规则是：

1. 完整历史必须可移植、可渲染。
2. 私有续接信息只用于同一 harness 或供应商的快速恢复。
3. 更换 harness 后允许只读查看或显式导入，不承诺无损继续正在执行的一轮。
4. 对已经产生但结果未知的外部副作用，默认标记中断并由用户确认，不自动重放。

## 对原 R1-R4 的裁剪建议

原先的“Engine”容易混淆模型供应商、agent runtime 和完整 harness。用户不会在产品界面中直接“换 Engine”，因此不应把它变成首版核心领域概念。

- “下一轮可以换 harness”：降级为产品配置能力。在一轮完成后启动另一个完整 agent 即可，不需要通用运行中迁移协议。
- “工具或决定持久化屏障处，同一轮换 harness”：首版删除。这要求两个不同 agent 共享工具语义、隐藏上下文、重试规则和副作用认知，成本高且四个项目都没有证明其必要性。
- “同一 harness 和版本用私有 checkpoint 快速恢复”：保留为可选优化，由各 harness 自己实现。
- “流式输出时瞬间换 harness”：明确不支持，但无需进入复杂设计；取消当前运行，再从已保存历史发起新一轮即可。

换句话说，不需要 R1-R4 组成一套通用切换协议。首版只需保证“历史不丢、旧对话能看、当前运行能取消、下一次可选择另一个 agent”。

## 推荐下一步

目前仍是讨论稿，不建议立刻开始大规模实现。下一步先做一份更短的架构决定记录，并做一个纵向原型：

1. 选 Pi RPC 或 Hermes Gateway 中一个，完整接入一次真实 BioinfoFlow 对话。
2. BioinfoFlow 只提供一个领域工具，例如“提交工作流”，让 harness 原生工具管线负责调用和批准。
3. 页面只实现输入、流式事件、批准弹窗、取消和历史回放。
4. 同时验证容器、挂载、网络和凭证硬边界。
5. 故意在工具执行前后杀掉进程，观察真实恢复需求，再决定是否需要更深的持久化协议。

原型通过后，再据此大刀阔斧删除平台中重复的工具状态机、审批状态机和抽象语义。这样不是被现有 BioinfoFlow 限制住，而是先用一个真实接入证明最小边界，再安全剪枝。
