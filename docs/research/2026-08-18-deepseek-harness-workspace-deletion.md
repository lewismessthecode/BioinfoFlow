# DeepSeek Harness Workspace 删除与磁盘目录生命周期

日期：2026-08-18

固定上游版本：[`deepseek-ai/deepseek-harness@dsh-v0.1.0-rc.7`](https://github.com/deepseek-ai/deepseek-harness/tree/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca)，commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`。

本文只使用该固定 commit 的上游源码、测试、包文档和官方 Agent Note。DeepSeek Harness 在这套功能中使用 `Workspace`，没有另一套独立的 `Project` 删除模型；本文中的“项目目录”指 Workspace 注册所引用的现有目录。

## 结论

DeepSeek Harness 的 `Delete workspace` 实际语义是**删除 Workspace 注册和分组元数据**，不是删除用户项目，也不是删除 Session：

- 用户工作目录和其中的文件始终保留；
- Live Session 和持久化 Session 日志始终保留，原 Workspace 下的 Session 转到 `Ungrouped`；
- 固定版本没有 Session 删除能力，只有非破坏性的 Archive；
- 没有“移到废纸篓”或“递归删除目录”选项；上游明确拒绝把它们混入 Workspace 删除；
- 删除前有确认框，文案明确告诉用户“从列表移除、目录和会话日志保留、会话进入 Ungrouped”。

这不是实现遗漏，而是刻意的所有权设计。上游的第一性原理是：Workspace 记录只是**注册了一个既有代码目录**，并不能证明 Harness 创建或拥有该目录；Session 日志又是独立持久化对象，因此 Workspace 记录没有权力递归删除二者。[上游决策记录](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/.agents/notes/implemented/feature/2026-07-27-workspace-registration-deletion.md#L7-L16)

## 1. Workspace、Project、Session 删除是否删除用户工作目录

| 操作 | 固定版本行为 | 用户工作目录 | Session / 日志 |
| --- | --- | --- | --- |
| `workspaceRegistry.delete(id)` / `workspace.delete` | 删除 Workspace 注册 | 保留 | 保留；Session 进入 `Ungrouped` |
| 重新注册同一路径 | 创建新 Workspace id | 复用原目录 | 不自动重新收编旧 Session |
| `archiveSession(id)` | 把 Session id 加入全局 archive set，从分组界面隐藏 | 不触碰 | Session、日志和原 Workspace 记账位置都保留 |
| Session delete | 固定版本不存在该能力 | 不适用 | 不适用；只有 Archive |
| Project delete | 没有独立于 Workspace 的 Project 删除 API | 不适用 | 不适用 |

Workspace 包的公开契约直接规定：删除只移除注册记录、持久顺序项和 Session account；目录、用户文件、live Sessions 与持久化日志“never touched”。同一路径重新注册会获得新 id，且不会自动重新采用保留的 Session。[Workspace 包文档](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/README.md#L9-L23)

实现中的 `delete()` 注释再次限定为“retaining its directory and every session log”；真正的 `deleteKnown()` 只改 Workspace domain state、实体 cache 和 `workspaces` 表，没有任何文件系统删除或 `SessionPersistence` 调用。[公开删除入口](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/src/index.ts#L191-L201)；[`deleteKnown()`](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/src/index.ts#L358-L401)

上游不仅写了单元测试，还用 Host API 测试验证删除后 Session 仍在 `session.list`、对应 Agent 仍 live、目录仍存在，并验证同一路径重新注册得到新 id、旧 Session 仍保留。[Host API 测试](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/host/apiproxy/tests/api-proxy-workspace.spec.ts#L498-L529)

端到端浏览器测试进一步在删除前后及页面 reload 后检查用户文件、JSONL 日志和当前 Session 都存在；UI 中的 Session 转到 `Ungrouped`。[Web E2E 测试](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/apps/web/tests/workspace-management.e2e.ts#L181-L264)

固定版本明确把 Session deletion 和 destructive folder removal 列为“separate, absent capabilities”；Workspace 删除不能替代它们。[Workspace 已知限制](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/README.md#L41-L44) Session UI 只有 Archive，没有 Session 删除或 unarchive 控件；Archive 不删除日志或 Workspace account。[Workspace UI 文档](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-workspace/README.md#L31-L35)；[Archive 实现](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/src/index.ts#L227-L254)

## 2. 实际删除的内部状态与临时目录

### Workspace 删除会删除什么

Workspace 删除只回收自己拥有的注册状态：

1. Workspace id 从持久 `workspaceIds` 顺序中移除；
2. 对应 `workspaces` 表记录删除；
3. 进程内 Workspace entity cache 条目删除；
4. 随 Workspace 行保存的有序 `sessionIds` account 一并消失；
5. 为 crash recovery 写入的 `pendingMutation` 在提交后清除；如果清除失败，删除仍算成功，下次启动幂等清理 marker。

这套提交边界、回滚与 marker 恢复语义由上游决策记录明确规定。[内部删除状态与提交点](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/.agents/notes/implemented/feature/2026-07-27-workspace-registration-deletion.md#L13-L25) 实现也保留全局 `archivedSessionIds`，只删除目标 Workspace 记录；表删除失败会恢复 cache 和旧 state。[`deleteKnown()` 状态变化](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/workspace/workspace/src/index.ts#L358-L400)

客户端只移除 Workspace projection；Session state 和当前 Session selection 是独立的，不会被 Workspace delta prune。客户端还保留进程内 tombstone，防止迟到事件或旧 baseline 把已删 Workspace 复活。[Client runtime 文档](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/runtime/README.md#L17-L25)

### Sandbox 临时目录是另一条生命周期

Workspace 删除本身**不删除任何临时目录**。Local Sandbox 的临时资源由 sandbox provider 生命周期独立管理：

- macOS Seatbelt 不为每个 Workspace 创建一个待删除的私有目录；它允许相应模式写系统 `/tmp` 和 `os.tmpdir()`。[macOS profile 文档](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/sandbox/sandbox-local/README.md#L11-L15)
- Windows `workspace-write` 为每个 live Session/Workspace pair 创建随机私有 temp 目录和可撤销 ACE；正常 provider dispose 时撤销 grant 并递归删除这些 provider-owned temp 目录。[临时 capability 创建](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/sandbox/sandbox-local/src/index.ts#L379-L442)；[provider dispose 清理](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/sandbox/sandbox-local/src/index.ts#L445-L482)
- 这项清理绑定 provider teardown，而不是 Workspace 删除。非正常崩溃可能留下随机 temp residue；新 provider 不复用它，之后由 OS temp hygiene 或人工回收。[崩溃残留策略](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/sandbox/sandbox-local/src/index.ts#L445-L452)

因此不能把“内部临时目录 GC”与“删除 Workspace 所引用的用户目录”混为一谈：前者由创建它的组件回收，后者不属于 Harness。

## 3. 保留、回收站与确认策略

### 显式保留

上游 UI 的中英文文案都明确承诺：只是从 Workspace 列表移除；folder 与 session logs 保留；Sessions 显示在 `Ungrouped`。[UI 文案](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-workspace/src/client/locales.ts#L107-L116)

### 没有回收站或目录删除

上游没有提供“Move folder to Trash”。决策记录明确拒绝这一方案，理由是 Workspace record 无法证明目录所有权；未来若加入破坏性文件操作，必须单独命名、单独确认，并有明确安全边界。[被拒绝的 Trash 方案](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/.agents/notes/implemented/feature/2026-07-27-workspace-registration-deletion.md#L39-L47)

### 确认交互

Workspace 删除有确认 Modal。文案必须说明三个后果；提交期间 Confirm 和 Cancel 禁用，重复提交被忽略，Escape/Close 不能中断；失败时 Modal 保留并显示错误，提交前 Cancel/Escape/Close 不执行删除。[确认策略](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/.agents/notes/implemented/feature/2026-07-27-workspace-registration-deletion.md#L31-L37) 组件测试锁定了这些行为及“等待 projection 真正移除后再关闭 Modal”的收敛语义。[确认组件测试](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-workspace/tests/workspace-browser.client.spec.tsx#L1051-L1101)

Session Archive 没有确认框，因为它被定义为非破坏性操作：日志和 account slot 都保留。[Archive UI 实现](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-workspace/src/client/WorkspaceBrowser.tsx#L930-L938)

## 4. 对 BioinfoFlow 的产品设计启示

### 第一性原理：按所有权图决定删除边界

“一个对象引用另一个对象”不等于“前者拥有后者并可销毁它”。建议把 BioinfoFlow 的删除边界拆成四层：

```text
用户磁盘项目目录       外部资源；Workspace 只引用，默认永远保留
Workspace 数据库记录   Workspace 自己拥有，可删除
Conversation/Session   是否由 Workspace 拥有，必须由产品契约明确决定
内部日志/工件/临时资源 由创建它们的 Session 或组件按各自生命周期回收
```

因此，**删除 Workspace 时保留磁盘目录**是更稳健的默认产品理念。BioinfoFlow 不能仅凭一个 path 字段推断目录由应用创建或可安全递归删除；目录可能是已有 Git checkout、共享目录、挂载点、用户主目录的子树，甚至同时被其他工具使用。

### DeepSeek 的 Session 策略不应被机械照搬

DeepSeek 保留 Session，是因为其产品契约把 Session persistence 视为独立对象，而且固定版本根本没有 Session deletion。BioinfoFlow 当前用户对“删除工作区”的预期显然不同：如果 Workspace 在 BioinfoFlow 的领域模型中**拥有**其 Conversation，并且产品动作仍叫“删除工作区”，那么更一致的语义是：

- 删除 Workspace 数据库记录；
- 级联删除该 Workspace 拥有的所有 Conversation/Session，以及只属于这些会话的日志、消息、tool rounds、审批、附件引用和其他内部记录；
- **不删除磁盘上的项目目录及用户文件**；
- 对共享 artifact/blob 使用引用计数或 GC，不能因删除一条 Workspace 记录而误删仍被其他对象引用的数据；
- 对正在运行的会话先取消并等待进入可删除状态，或明确拒绝删除，避免数据库消失但进程仍在写入。

反之，如果产品真正想保留会话，就应把动作改名为“从工作区列表移除”或“取消注册工作区”，并像 DeepSeek 一样把保留的会话明确移动到 `Ungrouped`。不能让按钮叫“删除工作区”，用户却仍在顶层看见原来的会话；这会同时制造语义错位和用户所报告的“没有删干净”体验。

### 推荐给 BioinfoFlow 的交互契约

结合当前缺陷描述，建议采用以下明确契约：

1. 主操作仍叫“删除工作区”，含义是删除 Workspace 与其拥有的全部会话数据。
2. 确认框显示影响数量和路径，例如：`将删除工作区“X”及其 4 个会话。磁盘目录 /path/to/X 和其中的文件不会被删除。`
3. 确认框把“会话数据会删除”和“磁盘目录会保留”分成两句，不用含混的“相关数据”。
4. 成功条件是服务端级联提交完成且前端 Workspace 与 Conversation projection 都已收敛；失败时保留确认框并允许重试。
5. 不在同一个 API 或按钮中加入目录删除。未来若确有需求，应另设“将项目目录移到废纸篓…”操作，使用可恢复的 OS Trash，并执行单独的高风险路径校验与二次确认；不要默认永久递归删除。

这样既修复“Workspace 删除后会话仍残留”的领域一致性问题，也保留 DeepSeek 最值得借鉴的安全边界：**数据库对象可以级联删除自己真正拥有的数据，但引用的用户目录默认不属于它。**
