# 最小而完整的 Agent Harness：运行闭环与工具面调研

日期：2026-08-13

## 调研范围

本文只回答两个问题：

1. 以 Pi 为主要模仿对象时，一个完整 Agent Harness 至少应拥有怎样的运行闭环？
2. 通用命令工具已经能完成很多事情，哪些工具仍值得独立存在？

DeepWiki 仅用于发现入口。Pi 结论均回到固定提交
[`46bb9a2c`](https://github.com/earendil-works/pi/tree/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106)
的官方源码和文档；对照资料来自 Claude Code 和 OpenAI 官方文档。

## 结论

BioinfoFlow 若要一次性重构成完整 Agent Harness，最简洁的参考答案不是拼装许多平台状态机，而是忠实复刻 Pi 已验证的闭环：

```text
用户输入
  -> 组装当前上下文
  -> 流式调用模型
  -> 模型返回文字或工具调用
  -> Harness 校验、确认并执行工具
  -> 工具结果成为正式对话消息
  -> 再次调用模型
  -> 没有工具调用时结束
```

这个闭环还必须统一拥有：会话历史、上下文压缩、重试、取消、运行中追加指令、工具并发策略、用户确认和同版本恢复。把其中任一段交回 BioinfoFlow 平台，都会重新产生两套相互穿插的 Agent 运行逻辑。

工具面不应膨胀。推荐默认只开放六类能力：

1. `read`：受控读取文字、图片等上下文。
2. `bash`：搜索、列目录、运行程序、测试、Git、网络客户端以及大量通用操作。
3. `edit`：可校验、可展示差异的精确局部修改。
4. `write`：创建或完整覆盖文件。
5. `ask_user`：暂停 Agent 闭环，等待用户选择或确认。
6. 极少量 BioinfoFlow 业务工具：只覆盖身份、权限、凭证、持久状态和稳定审计边界。

`grep`、`find`、`ls` 不需要默认成为独立工具；Pi 自己也把它们视为可选只读便利工具，默认编码工具仍只有 `read`、`bash`、`edit`、`write`。搜索和列目录由 `bash` 中的 `rg`、`find`、`ls` 完成即可。[Pi README](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/README.md#L15-L19)明确称 Pi 为最小 Harness，并说明默认四工具；[工具注册源码](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/index.ts#L81-L175)区分了默认编码工具和可选只读工具。

## 一、Pi 的完整运行闭环

### 1. 单一模型—工具循环

Pi 的核心循环只有一份：先处理运行中排队的用户消息，再流式生成助手消息；若助手消息包含工具调用，就执行工具、把工具结果加入上下文，然后继续下一次模型调用；没有工具调用且没有后续消息时结束。[`agent-loop.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent-loop.ts#L155-L275)

模型响应、工具调用和工具结果不是外围日志，而是同一份正式对话的一部分。Pi 的会话格式保存用户消息、助手文字、思考块、工具调用、工具结果、自定义消息和压缩摘要，并用树形 `id`/`parentId` 支持分支。[`session-format.md`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/session-format.md#L1-L171)

因此 BioinfoFlow 不应再另建一套平台级“工具意图—工具动作—工具结果”循环。Harness 自己的正式历史就是恢复、渲染和继续思考的事实来源。

### 2. Harness 自己拥有运行控制

Pi `Agent` 暴露 `prompt()`、`continue()`、运行中引导、后续消息、取消和等待空闲等操作；执行时由同一个 `AbortSignal` 贯穿模型请求和工具执行。[`agent.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent.ts#L347-L508)

Pi 的 RPC 模式让外部产品通过 JSONL 发送输入、运行中引导、后续消息和取消，并接收流式 Agent 事件；官方同时建议 Node/TypeScript 应用可直接嵌入 `AgentSession`。[`rpc.md`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/rpc.md#L1-L116)

这证明平台最自然的位置是输入和界面适配层，不是循环的中间控制者。

### 3. 工具调用的完整管线属于 Harness

Pi 在执行工具前完成：

- 根据工具名查找实现；
- 预处理和校验结构化参数；
- 调用执行前拦截器；
- 允许拦截器阻止调用；
- 将取消信号传给工具；
- 收集流式进展；
- 标准化成功或错误结果；
- 调用执行后拦截器；
- 把结果转成正式工具结果消息。

见 [`agent-loop.ts` 的工具准备与执行路径](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent-loop.ts#L560-L760)。

Pi 的扩展事件直接挂在这条管线上。官方示例在 `tool_call` 事件中识别危险命令，通过 `ctx.ui` 询问用户，并返回 `block` 阻止执行，而不是把工具调用移交给另一个平台运行器。[`permission-gate.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/examples/extensions/permission-gate.ts#L1-L34)

### 4. 并行不是平台调度问题

Pi 的默认规则很小：

- 工具批次默认可以并行；
- 如果全局配置为串行，整批串行；
- 如果批次中任何工具声明自己必须串行，整批串行；
- 并行执行时仍按模型原始调用顺序把工具结果写回对话。

见 [`agent-loop.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/src/agent-loop.ts#L411-L555)。

文件修改再增加一个局部规则：同一文件上的修改排队，不同文件仍可并行。[`file-mutation-queue.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/file-mutation-queue.ts#L28-L60)

这比建立通用工具批次、动作租约和平台调度状态机更符合奥卡姆剃刀：默认并行，声明串行例外，同资源冲突在工具实现内处理。

### 5. 上下文压缩不删除历史

Pi 在上下文接近窗口上限时，把旧内容总结成结构化摘要，同时保留最近消息；摘要作为新条目追加，原历史仍在会话文件中。后续请求只使用摘要和保留的最近消息。[`compaction.md`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/compaction.md#L1-L113)

因此“历史保存”和“发给模型的当前上下文”必须分开：历史完整保存，模型输入只是从历史派生的当前视图。

### 6. 恢复状态应是 Harness 的私有实现

Pi 当前可用的 Coding Agent 通过完整会话条目恢复对话、模型选择、压缩摘要和分支；其新 Durable AgentHarness 规格进一步把永久会话条目、当前运行状态和用量账本分开，并用“意图提交—外部效果—结果提交”处理崩溃窗口。[`harness.md`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/agent/docs/harness.md#L95-L240)

但这一 Durable AgentHarness 的当前核心入口仍未实现，不能直接当成现成依赖。因此适合模仿它的原则，而不是复制全部未落地结构。BioinfoFlow 的最简实现应保存完整历史，并让当前 Harness 保存同版本恢复所需的少量私有状态；旧对话渲染不得依赖私有状态。

## 二、最小工具面

### 1. `bash`：开放世界的通用工具

Pi 的 `bash` 描述明确把 `ls`、`grep`、`find` 等列为命令工具覆盖的行为。它在当前目录执行命令，支持超时、取消、标准输出和错误流、输出截断以及完整输出落临时文件。[`bash.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/bash.ts#L41-L80)和[`createBashToolDefinition`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/bash.ts#L322-L420)

OpenAI 官方 Shell 工具同样把终端视为完整执行环境，既可以使用托管容器，也可以由应用执行本地 `shell_call`，捕获输出、错误、退出码和超时后把 `shell_call_output` 送回模型。[OpenAI Shell](https://developers.openai.com/api/docs/guides/tools-shell#local-shell-mode)

因此以下能力不需要分别造工具：

- 列目录、按名称找文件、全文搜索；
- Git 操作；
- 运行测试、编译器、格式化器；
- Python、R、Nextflow、MiniWDL 和其他领域命令；
- 调用 `bif` CLI；
- 使用 `curl`、`jq` 等通用客户端；
- 临时数据处理、统计和格式转换。

只要命令运行在 BioinfoFlow 提供的受控工作环境中，一个 `bash` 就能覆盖大部分计算与开发能力。

### 2. 为什么仍要独立 `read`

普通文本技术上可以用 `cat` 或 `sed` 读取，但独立 `read` 仍有四个价值：

- 参数比 shell 命令更稳定，模型不必处理转义；
- 可以统一分页和截断，避免巨量输出污染上下文；
- 可以识别并发送图片等多模态内容；
- 可以成为文件访问策略和展示层的明确语义点。

Pi 自己的系统提示要求优先用 `read` 而不是 `cat` 或 `sed`，并支持按行分页和图片检测。[`read.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/read.ts#L21-L68)

Claude Code 的 `Read` 还支持图片、PDF 和笔记本，进一步证明它不是普通命令输出的简单别名。[Claude Code Read](https://code.claude.com/docs/en/tools-reference#read-tool-behavior)

### 3. 为什么仍要独立 `edit`

模型当然可以用 Python、Perl 或 `sed -i` 修改文件，但独立 `edit` 提供了命令工具难以统一保证的行为：

- 修改前以精确旧文本作为乐观并发检查；
- 要求目标唯一，防止误改多个位置；
- 一次表达多个互不重叠的局部修改；
- 返回标准差异，便于用户查看和审计；
- 同一文件修改自动串行。

Pi 的 `edit` 直接实现这些约束，并返回展示差异和统一补丁。[`edit.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/edit.ts#L36-L95)及[执行实现](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/edit.ts#L298-L370)

Claude Code 也把 `Edit` 定义为精确字符串替换，要求匹配和唯一性，并在适用时执行“先读后改”。[Claude Code Edit](https://code.claude.com/docs/en/tools-reference#edit-tool-behavior)

### 4. 为什么保留 `write`

`write` 只做一件事：创建文件或完整覆盖文件，并自动建立父目录。它适合新文件和整体生成；已有文件的局部变化仍用 `edit`。[Pi `write.ts`](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/src/core/tools/write.ts#L187-L240)；[Claude Code Write](https://code.claude.com/docs/en/tools-reference#write-tool-behavior)

它不是绝对必需，但保留后工具职责非常清楚：`edit` 负责局部变化，`write` 负责完整内容。这样可以避免模型用复杂 shell heredoc 处理大量转义，也便于界面展示将要写入的内容。

### 5. `ask_user` 不能由 `bash` 代替

用户交互是运行控制，不是计算命令。它需要：

- 暂停当前 Agent；
- 把问题和选项发到网页；
- 等待可能很久以后到来的回答；
- 接受取消；
- 把回答作为正式上下文继续模型—工具循环。

Pi 扩展通过 `ctx.ui.select()`、`confirm()` 和 `input()` 在工具执行管线中完成交互；无界面时可以按策略阻止调用。[Pi 扩展文档](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/extensions.md#L60-L82)

Claude Code 也提供独立的 `AskUserQuestion`，问题在用户回答前保持打开，并明确区别于权限提示。[Claude Code AskUserQuestion](https://code.claude.com/docs/en/tools-reference#askuserquestion-tool-behavior)

实现上，普通澄清问题和危险操作确认可以共用一套 Harness 用户交互通道，不必为“提问”“审批”“计划确认”分别建设状态机。

### 6. 什么情况下才增加 BioinfoFlow 业务工具

OpenAI 官方把 Shell 和自定义函数明确分开：Shell 用于完整终端环境；函数调用用于让应用以结构化参数执行自己的代码和能力。[OpenAI Tools](https://developers.openai.com/api/docs/guides/tools#available-tools)和[Function calling](https://developers.openai.com/api/docs/guides/function-calling)

对 BioinfoFlow，只有满足下列任一条件的行为才值得成为独立业务工具：

- 必须绑定当前登录用户、团队或项目身份；
- 必须由服务端重新校验业务权限；
- 需要受控使用平台保存的凭证；
- 会改变 BioinfoFlow 数据库中的持久状态；
- 需要稳定参数、返回结构和审计语义；
- 不能安全地把能力暴露给容器内任意进程。

典型候选是“提交工作流运行”和“请求受保护的数据或连接”。反过来，查询目录、读日志、运行 Nextflow、分析结果、调用公开 API 等，应优先由 `bash` 或 `bif` CLI 完成。

不要为每个数据库表或 CLI 子命令造一个工具。可以把多个低风险只读查询收敛进 `bif` CLI；只有少数真正穿越业务边界的写操作使用结构化工具。

## 三、权限和安全边界

Harness 应拥有工具确认规则和用户交互，但这些规则不是不可绕过的安全边界。

Pi 官方明确说明它没有内置沙箱，所有工具和扩展都继承 Pi 进程权限；真实隔离必须来自操作系统、容器、虚拟机、只读挂载、最小凭证和网络限制。[Pi Security](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/docs/security.md#L31-L53)

Claude Code 也指出，对 Bash 中可识别的文件命令可以应用部分路径规则，但 Python、Node 等任意子进程的间接读写无法靠命令识别全面阻止；覆盖所有进程需要操作系统沙箱。[Claude Code Edit 说明](https://code.claude.com/docs/en/tools-reference#edit-tool-behavior)

OpenAI Shell 文档同样要求沙箱、允许或拒绝规则、日志和网络范围控制。[OpenAI Shell](https://developers.openai.com/api/docs/guides/tools-shell#risks-and-safety)

因此最简单且正确的分工是：

- Harness 决定何时确认、如何展示、用户拒绝后怎样继续思考。
- BioinfoFlow 工作环境决定进程能看到哪些文件、网络和凭证。
- BioinfoFlow 业务服务对每次受保护操作重新鉴权。

三者不是三套审批系统，而是交互策略、运行隔离和业务授权三个不同层次。

## 四、推荐给 BioinfoFlow 的最小实现

### Harness 必须一次性完整拥有

1. 一份正式、可持久化的会话历史。
2. 从历史派生模型上下文的组装器。
3. 模型流式调用和供应商适配。
4. 完整模型—工具—模型循环。
5. 工具注册、按会话开放和结构化参数校验。
6. 执行前确认、执行、结果标准化和回填。
7. 默认并行、工具可声明串行、同资源冲突局部排队。
8. 运行中引导、后续消息、取消和超时。
9. 上下文压缩，但永不删除永久历史。
10. 模型错误重试和明确终止原因。
11. 同版本恢复所需的私有状态。
12. 流式文字、工具进展、用户问题、完成和错误事件。

### 默认工具

```text
read
bash
edit
write
ask_user
```

再按真实业务边界增加极少数 BioinfoFlow 工具。首批不建议把 `grep`、`find`、`ls`、待办清单、计划模式、子 Agent、网页搜索、浏览器和每个 BioinfoFlow API 都做成默认工具。

Pi 自己明确跳过内置子 Agent 和计划模式，鼓励按真实需要通过扩展增加，而不是让核心预装一切。[Pi README](https://github.com/earendil-works/pi/blob/46bb9a2c3bdb296b0d2179f7309ec6b79a7f3106/packages/coding-agent/README.md#L15-L19)

这不是留下“下次返工”，而是把完整性定义正确：完整 Harness 是闭环完整，不是功能数量无限。未来增加网页、电脑操作或子 Agent 时，应作为新能力接入同一个成熟循环，不需要改写循环。

## 五、可直接转入重构计划的判断

1. 以 Pi 为主要模仿对象，比抽取 Pi、Hermes、Claude、Codex 的最大公约数更简单。
2. 复刻的是 Pi 的职责边界和运行闭环，不是照搬它尚未完成的 Durable AgentHarness 全部规格。
3. BioinfoFlow 应实现一个完整 Harness，而不是一个仅产出工具意图的模型适配器。
4. 工具调用、并发、确认、执行、结果回填、重试、压缩和恢复全部留在 Harness。
5. BioinfoFlow 平台只提供工作环境、业务服务、身份权限、持久存储和网页适配。
6. 默认五工具足够支撑完整 Agent；新增专用工具必须证明 `bash` 或现有工具无法清晰、安全地表达。
7. 永久历史与私有恢复状态分开保存；前者负责长期渲染，后者负责同版本继续。
8. 安全不依赖提示词或命令字符串识别，而依赖容器、挂载、网络、最小凭证和服务端鉴权。

大道至简在这里不是减少必要能力，而是把所有 Agent 行为收拢到唯一闭环，把开放世界工作收敛到一个命令工具，只为真正不同的语义保留少数独立工具。
