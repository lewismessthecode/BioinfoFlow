# 2026 年 AI Coding、Git Worktree 与最简可靠 CI/CD 研究

日期：2026-08-15

范围：Codex、Claude Code、多分支、多 worktree、多 feature、多 agent 并行开发，以及 BioinfoFlow 的 GitHub Actions / Release Please 架构。

证据标签：

- **官方事实**：来自 Git、GitHub、Google Release Please、OpenAI、Anthropic、Semantic Versioning 的一手官方资料。
- **仓库证据**：来自 BioinfoFlow 已提交的 workflow/config、GitHub API 或 Actions 运行记录。
- **BioinfoFlow 推论/建议**：基于官方事实和仓库证据作出的工程判断，不冒充官方规定。

## 结论先行

1. **一个独立 feature 或写入型 agent，应独占一个 worktree、一个分支和一个 PR。** Git worktree 隔离工作目录，但共享仓库元数据；Git 默认拒绝让同一分支同时被多个 worktree 检出。Codex 和 Claude Code 都把 worktree 作为并行写入隔离边界。[Git 官方文档](https://git-scm.com/docs/git-worktree) [OpenAI Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) [Claude Code worktrees](https://code.claude.com/docs/en/worktrees)
2. **读密集型任务适合 subagent 并行，写密集型任务必须缩小写入所有权或使用独立 worktree。** OpenAI 明确建议先把并行 agent 用于探索、测试、分诊和总结，并警告并行写入会增加冲突和协调成本；Claude Code 也提供 `isolation: worktree` 来隔离写入型 subagent。[OpenAI Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) [Claude Code subagents](https://code.claude.com/docs/en/sub-agents) [Claude Code worktree isolation](https://code.claude.com/docs/en/worktrees#isolate-subagents-with-worktrees)
3. **CI 的核心职责是回答“这个 PR 的合并结果是否可安全进入 main”。** GitHub 的 `pull_request` 默认检出 PR merge branch，因此测试的是与目标分支合并后的结果；required check 必须出现在最新相关 SHA 上。[GitHub `pull_request`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request) [Required checks troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
4. **Release Please 应只负责版本、CHANGELOG、tag 和 GitHub Release；发布镜像/安装器是后续 CD。** Release Please 官方明确说它不负责发布到包管理器或复杂分支管理；合并 Release PR 后，它更新版本和 changelog、打 tag、创建 GitHub Release。[Release Please README](https://github.com/googleapis/release-please#release-please)
5. **BioinfoFlow 当前最明确的问题不是版本号，而是 Release PR 的 CI 触发链。** Release Please 使用 `GITHUB_TOKEN` 创建/更新 PR 时，自然 `pull_request` CI 会进入 `action_required`；另行 `workflow_dispatch` 虽能执行，但不是 PR 上自然产生的 required check。[GitHub 递归触发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow) [PR #220](https://github.com/lewismessthecode/BioinfoFlow/pull/220)
6. **最简方向是：自然 PR CI + 一个稳定 required gate + Release Please 专用凭证 + 直接调用 reusable publication workflow。** 不再用 `gh workflow run` 模拟 PR CI，也不再用多次 dispatch 串联正式发布。[Reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) [GITHUB_TOKEN permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
7. **若 `main` 镜像没有真实消费者，删除每次 main push 的镜像发布最简单。** 若必须保留，则应使用当前 GitHub concurrency 支持的 `queue: max`，避免默认 `queue: single` 替换中间 pending run。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 第一性原理与奥卡姆剃刀

可靠交付只有五个状态转换：

```text
独立 worktree/branch
  -> Pull Request
  -> PR CI 证明合并结果可用
  -> main
  -> Release PR 决定版本与发布内容
  -> 不可变 tag/GitHub Release
  -> 发布并验证该 tag 的镜像和安装器
```

**BioinfoFlow 推论：** 每个转换只保留一个权威触发器和一个职责所有者：

- PR 安全性只由自然 `pull_request` CI 判断；不要再额外 dispatch 一个“看起来像 CI”的运行。[GitHub `pull_request`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
- Release Please 只维护 Release PR，并在其合并后创建 tag/release。[Release Please README](https://github.com/googleapis/release-please#whats-a-release-pr)
- 发布工作只消费不可变 tag，不从可变分支重新猜测版本或源代码状态。[Semantic Versioning](https://semver.org/#spec-item-3) [Release Please README](https://github.com/googleapis/release-please#whats-a-release-pr)
- 所有修改共享外部状态的 CD 都应串行；普通 PR CI 可并行并取消同分支旧运行。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

## 多 worktree、多 feature、多 agent 最佳实践

### Git worktree

**官方事实：** 一个仓库可以有一个主 worktree 和多个 linked worktree；每个 worktree 有独立的 `HEAD`、index 和工作目录，但共享仓库历史。Git 默认拒绝在新 worktree 中检出已经被另一 worktree 占用的分支。[Git 官方 `git-worktree`](https://git-scm.com/docs/git-worktree)

**BioinfoFlow 建议：**

- 固定映射：`1 feature = 1 owner/agent = 1 worktree = 1 branch = 1 PR`。
- 开工前运行 `git branch --show-current` 与 `git worktree list`；不要在 worktree 中假设自己拥有 `main`。
- 每个 agent 只 rebase、reset 或 force-push 自己的 feature branch；共享集成通过 PR 和 main 完成。
- 长期 worktree 用 `git worktree lock`；正常清理用 `git worktree remove`，目录被手工删除后再用 `git worktree prune`，路径搬移后用 `git worktree repair`。[Git 官方 `git-worktree`](https://git-scm.com/docs/git-worktree)
- 每个 worktree 使用不同端口、数据库/data 目录和运行时状态目录；worktree 只隔离文件，不会自动隔离端口、容器名或外部服务。这是基于 worktree 只提供独立 checkout 的 **BioinfoFlow 推论**。[Git 官方 `git-worktree`](https://git-scm.com/docs/git-worktree)

### OpenAI Codex

**官方事实：** Codex managed worktree 默认从所选分支的 `HEAD` 创建并处于 detached HEAD；同一分支不能同时存在于多个 worktree。被 Git 忽略但新 worktree 必需的文件可通过 `.worktreeinclude` 复制。[OpenAI Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)

**官方事实：** Codex 会从项目根目录向当前目录加载 `AGENTS.md` / `AGENTS.override.md`，越靠近当前目录的指导越具体；官方建议把规则写得简洁，并把格式化/lint 交给 CI。[OpenAI `AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

**官方事实：** Codex subagent 适合有边界的探索、测试、分诊和总结；并行写入型工作需要更谨慎，因为会增加冲突与协调成本。[OpenAI Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) [OpenAI best practices](https://learn.chatgpt.com/guides/best-practices#organize-long-running-chats)

**BioinfoFlow 建议：** 根 `AGENTS.md` 只保留所有 agent 都必须遵守的仓库契约；后端、前端或发布领域的细则放到靠近代码的文件。研究、审查、测试代理默认只读；写入代理必须获得明确文件所有权或独立 worktree。

### Anthropic Claude Code

**官方事实：** Claude Code 支持项目级 `CLAUDE.md` / `.claude/CLAUDE.md`、用户级 `~/.claude/CLAUDE.md` 和本地 `CLAUDE.local.md`；官方建议具体、简洁、结构化，并把大型或路径相关规则拆到 `.claude/rules/`。[Claude Code memory](https://code.claude.com/docs/en/memory)

**官方事实：** `claude --worktree feature-auth` 会创建隔离 worktree 和独立分支；`isolation: worktree` 可让 subagent 在独立 worktree 中写入。[Claude Code worktrees](https://code.claude.com/docs/en/worktrees)

**官方事实：** Claude Code hooks 已提供 `SubagentStart`、`SubagentStop`、`WorktreeCreate` 和 `WorktreeRemove` 事件；`WorktreeCreate` 可替换默认 Git 创建逻辑。[Claude Code hooks](https://code.claude.com/docs/en/hooks)

**BioinfoFlow 建议：** hooks 只用于确定性的护栏和环境初始化，例如创建独立端口配置、验证 worktree 路径、阻止写入主 checkout；不要让 hook 隐式执行 rebase、merge 或发布。

## GitHub Actions 官方事实

### `pull_request`

默认 activity 为 `opened`、`synchronize`、`reopened`；默认 checkout 指向 `refs/pull/<n>/merge`，因此 CI 验证 PR 与 base 的测试合并结果。[GitHub `pull_request`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)

### `GITHUB_TOKEN` 递归触发

`GITHUB_TOKEN` 产生的大多数事件不会再次创建 workflow run。当前官方规则对 `workflow_dispatch` / `repository_dispatch` 例外；用 `GITHUB_TOKEN` 创建或更新 PR 时，`opened` / `synchronize` / `reopened` 的运行会被创建为需要人工批准的 `action_required` 状态。GitHub App installation token 或 PAT 可让这些 PR workflow 自动运行。[GitHub trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)

### Required checks

Required checks 必须针对最新相关 SHA，并达到 `success`、`skipped` 或 `neutral`。若整个 workflow 因 path/branch filter 未触发，关联 check 会保持 Pending；若 job 由条件跳过，则 job 会报告 Success。因此 required workflow 不应使用可能让整个 workflow 消失的路径过滤，适合使用内部选择性 job 加一个总 gate。[Required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging) [Troubleshooting required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)

GitHub 还要求 required job 名称在所有 workflow 中保持唯一，否则可能产生歧义并阻塞合并。[Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

### Reusable workflows / `workflow_call`

Reusable workflow 通过 `on: workflow_call` 暴露，并在 caller 的 job 级 `uses` 中直接调用；同仓库调用使用调用者同一 commit 的 workflow。调用者传入的 `GITHUB_TOKEN` 权限只能保持或降低，不能在被调用 workflow 中提升。[Reuse workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) [Reusing workflow configurations](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)

### Concurrency

当前 GitHub 文档定义：同一 concurrency group 同时最多一个 running；`queue: single` 是默认值，最多保留一个 pending，新 pending 会替换旧 pending；`queue: max` 最多保留 100 个 pending。`queue: max` 不能与 `cancel-in-progress: true` 同时使用。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

### Merge queue

启用 merge queue 后，所有 required GitHub Actions workflow 必须监听独立的 `merge_group` 事件，否则队列中的 required checks 不会产生并导致合并失败。Merge queue 会在最新 base 与队列中前序 PR 的组合上再次验证 required checks。[GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) [GitHub `merge_group`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#merge_group)

### Least privilege

GitHub 建议默认只给 `GITHUB_TOKEN` 仓库 contents read，并按 job 提升到最小必要权限；第三方 action 若要获得不可变引用，应固定到完整 commit SHA。[GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use) [GITHUB_TOKEN authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)

## Release Please 与版本号

**官方事实：** Release Please 从 Conventional Commits 推导 release PR；Release PR 会随着 main 的新增提交持续更新，只有合并它才会更新 changelog/版本、创建 tag 和 GitHub Release。[Release Please README](https://github.com/googleapis/release-please#whats-a-release-pr)

**官方事实：** `bump-minor-pre-major: true` 让 1.0 前的 breaking change 走 minor；`bump-patch-for-minor-pre-major: true` 才会让 1.0 前的 `feat` 改走 patch。[Release Please manifest configuration](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md)

**仓库证据：** BioinfoFlow 当前配置为 `bump-minor-pre-major: true`、`bump-patch-for-minor-pre-major: false`，并隐藏 `refactor`、`docs`、`test`、`chore`、`ci`、`build` changelog section。[release-please-config.json](https://github.com/lewismessthecode/BioinfoFlow/blob/main/release-please-config.json)

**BioinfoFlow 推论：** `0.2.0 -> 0.3.0` 是预期行为：0.2.0 后存在 `feat: add composer context usage meter`，而 `feat` 在现有配置中触发 minor。SemVer 官方 FAQ 也把 0.y.z 阶段“每次发布递增 minor”视为最简单做法，因此版本号本身不是异常。[Semantic Versioning 0.y.z FAQ](https://semver.org/#how-should-i-deal-with-revisions-in-the-0yz-initial-development-phase) [PR #220](https://github.com/lewismessthecode/BioinfoFlow/pull/220)

**BioinfoFlow 推论：** 0.3.0 曾漏掉大型 agent harness 重构的原因是该提交使用 `refactor:`，而配置明确隐藏该 section；这是 changelog 分类/策展问题，不是版本算法问题。[release-please-config.json](https://github.com/lewismessthecode/BioinfoFlow/blob/main/release-please-config.json) [0.2.0...main commits](https://github.com/lewismessthecode/BioinfoFlow/compare/0.2.0...main)

建议继续把纯内部整理标为 `refactor` 并隐藏；会改变用户能力或体验的工作应使用 `feat` / `fix`。特殊情况下可在合并 PR 中使用 Release Please 官方 commit override，而不是长期把所有 refactor 都塞进用户 changelog。[Release Please commit override](https://github.com/googleapis/release-please#how-can-i-fix-release-notes)

Release 节奏应由“何时合并 Release PR”控制，而不是通过扭曲 SemVer 来控制；Release PR 不应自动合并。[Release Please README](https://github.com/googleapis/release-please#whats-a-release-pr)

## BioinfoFlow 当前仓库证据与问题推论

### 1. Branch protection

**仓库证据：** 2026-08-15 读取 classic branch protection API 得到 `strict=true`，required contexts 为 `backend`、`docker`、`frontend`；rulesets API 返回空数组。[Main protection API](https://api.github.com/repos/lewismessthecode/BioinfoFlow/branches/main/protection) [Rulesets API](https://api.github.com/repos/lewismessthecode/BioinfoFlow/rulesets)

**BioinfoFlow 推论：** strict 模式在多 agent 高频合并时会造成反复更新分支和重跑 CI；若并行 PR 数量持续上升，merge queue 更适合把“在最新 main 上验证”集中交给 GitHub 队列。[Required checks strict mode](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging) [Merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)

### 2. Release PR 的 CI 不是自然闭环

**仓库证据：** PR #220 的自然 `pull_request` CI run [31843479735](https://github.com/lewismessthecode/BioinfoFlow/actions/runs/31843479735) 和 CodeQL run [31843479762](https://github.com/lewismessthecode/BioinfoFlow/actions/runs/31843479762) 都以 `action_required` 结束且 jobs 为空。Release workflow 手工 dispatch 的 CI run [31843477899](https://github.com/lewismessthecode/BioinfoFlow/actions/runs/31843477899) 在同一 SHA `e87c4e1...` 上真正执行，并因 backend 测试失败而失败。

**仓库证据：** 当前 `release-please.yml` 使用 `${{ secrets.RELEASE_PLEASE_TOKEN || secrets.GITHUB_TOKEN }}`，在 Release PR 创建/更新后执行 `gh workflow run ci.yml --ref "$head_branch"`。[release-please.yml](https://github.com/lewismessthecode/BioinfoFlow/blob/main/.github/workflows/release-please.yml)

**BioinfoFlow 推论：** 手工 dispatch run 能发现真实失败，但它不是 PR 的自然 `pull_request` required check；因此同时出现“PR 上 required contexts 不满足”和“另一个 Actions 页面中 CI 已运行”的双重状态。根因符合 GitHub 对 `GITHUB_TOKEN` 自动 PR 的 `action_required` 规则。[GitHub trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)

### 3. Merge queue 尚未接入

**仓库证据：** 当前 [ci.yml](https://github.com/lewismessthecode/BioinfoFlow/blob/main/.github/workflows/ci.yml) 和 [codeql.yml](https://github.com/lewismessthecode/BioinfoFlow/blob/main/.github/workflows/codeql.yml) 都没有 `merge_group`。

**BioinfoFlow 推论：** 当前未启用 merge queue 时这不是故障；如果启用 merge queue，必须在同一次变更中给所有 required workflows 增加 `merge_group`，否则队列会等待永远不会报告的 checks。[GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)

### 4. Main 镜像发布存在 pending-run 替换竞态

**仓库证据：** [container-release.yml](https://github.com/lewismessthecode/BioinfoFlow/blob/main/.github/workflows/container-release.yml) 同时监听每次 `main` push 和 `workflow_call`；concurrency group 为 `container-release-${{ github.ref }}`，`cancel-in-progress: false`，且 `auto` 模式只比较单次 push 的 `github.event.before..GITHUB_SHA`。

**BioinfoFlow 推论/竞态风险，并非已证实事故：** 假设 run A 正在发布，随后 backend 变更 B 进入 pending，再随后 frontend-only 变更 C 进入同一 group。默认 `queue: single` 会用 C 替换 pending 的 B；A 完成后 C 只检查 `B..C`，可能判断 backend 未变化，于是 B 的 backend 变化没有任何 main-image run 负责发布。[GitHub concurrency 默认 pending 语义](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

**正确性选项：** 若必须保留每次 main push 镜像发布，可设置 `queue: max`、保持 `cancel-in-progress: false`，让最多 100 个 pending run 按队列保留；也可改为从“最后成功发布 SHA”累计比较，但这需要额外状态管理。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

**奥卡姆判断：** 如果没有用户或环境实际消费 `main` / `sha-*` 镜像，直接删除 main-push image CD，只发布不可变 release tag 镜像，比引入发布游标和恢复逻辑更简单可靠。

## 推荐的最简可靠架构

### A. `ci.yml`：唯一 PR CI 入口

- 触发：`pull_request`、`push: main`、手工恢复用 `workflow_dispatch`；只有在决定启用 merge queue 时再增加 `merge_group`。[GitHub events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- 保留内部 changed-area 检测和选择性 leaf jobs，但把 branch protection 收敛为一个始终产生的稳定 gate，例如 `ci / required`；gate 使用 `if: always()` 汇总 backend/frontend/docker/installer/workflow checks。[Required checks troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- 不在 required workflow 的 `on` 上使用 paths filter；docs-only PR 由内部逻辑快速通过 gate。[Required checks troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks)
- PR concurrency 可取消同一 PR 的旧运行；这类 CI 只关心最新提交。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

### B. `release-please.yml`：版本与 Release PR

- 使用专用 GitHub App installation token；PAT 是官方支持的备选，但 GitHub App 的短期、可精确授权凭证更符合 least privilege。[GitHub trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow) [Release Please Action credentials](https://github.com/googleapis/release-please-action#github-credentials)
- 删除 “Dispatch CI for release pull request”；由专用凭证产生自然 `pull_request` CI，使 checks 自动关联 PR。
- 删除 `actions: write`；仅给 Release Please job 所需的 `contents`、`pull-requests`、`issues` 写权限。[Release Please Action example](https://github.com/googleapis/release-please-action#basic-configuration) [GitHub least privilege](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token#modifying-the-permissions-for-the-github_token)
- Release PR 保持人工合并，作为发布节奏和 changelog 策展门。

### C. `publish-release.yml`：一个 reusable publication workflow

- 使用 `workflow_call` 接收 version/tag，并保留可选 `workflow_dispatch` 作为恢复入口；Release Please 的 `release_created` 输出直接在 job 级调用它，不再 `gh workflow run` 多跳 dispatch。[Reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) [Release Please outputs](https://github.com/googleapis/release-please-action#outputs)
- 只 checkout 不可变 numeric tag；一次完成镜像构建、installer assets、跨架构/安装 smoke 和 release asset 上传。
- 全局串行正式发布：固定 concurrency group，例如 `release-publish`，`cancel-in-progress: false`，并用 `queue: max` 防止多个待发布版本互相替换。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- 权限按 job 分配：验证 job `contents: read`，镜像 job `packages: write`，上传 assets job `contents: write`。[GitHub least privilege](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token#modifying-the-permissions-for-the-github_token)

### D. Main 镜像

- 首选：若无真实需求，移除 `container-release.yml` 的 `push: main` 路径，只保留正式 release publication。
- 若确实存在 staging 或开发者消费 `main` tag：拆成独立 main-image workflow，并使用 `queue: max`；不要与正式 release publication 共用同一变化检测和生命周期。[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

### E. Merge queue

- 多 agent 并行 PR 已经造成频繁 main 变化时，建议启用 merge queue，减少每个 agent 手工 rebase 和 strict-check 重跑。
- 启用动作必须原子化：CI 和所有 required CodeQL workflow 同时增加 `merge_group`，然后再打开 merge queue 规则。[GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- 若当前合并量不高，暂不启用；保留现有 strict protection 比提前增加队列机制更符合奥卡姆剃刀。

### F. Auto merge 与安全加固

- GitHub repository 已支持原生 auto-merge；如果 label 驱动不是明确产品需求，可移除自定义 Auto Merge workflow，减少一个 `pull_request_target` 写权限入口。若保留，继续禁止 checkout/执行 PR 代码。[GitHub `pull_request_target` security](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target) [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use#mitigating-the-risks-of-untrusted-code-checkout)
- 逐步把第三方 actions 固定到完整 commit SHA，并让 Dependabot 更新 SHA；这是安全加固，不应阻塞先修复 Release PR CI 闭环。[GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions)

## 推荐实施顺序

1. **P0：修复 Release PR CI 关联。** 配置专用 Release Please 凭证，删除手工 dispatch PR CI。
2. **P1：收敛 required checks。** 增加一个稳定 `ci / required` gate，并原子更新 classic branch protection。
3. **P2：合并发布链。** 用 `workflow_call` 直接调用一个 publication workflow，删除多跳 dispatch；正式发布使用 `queue: max` 串行。
4. **P3：决定 main 镜像是否有消费者。** 无则移除；有则独立 workflow 并使用 `queue: max`。
5. **P4：根据并行 PR 量决定 merge queue。** 只有启用时才添加 `merge_group`，并同时覆盖 CI/CodeQL required workflows。
6. **P5：least privilege 与 action SHA pinning。** 作为结构简化后的安全加固。

## 官方资料清单与可用性

- Git：[`git-worktree`](https://git-scm.com/docs/git-worktree)
- GitHub Actions：[`pull_request` / `merge_group`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)、[`GITHUB_TOKEN` 递归触发](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)、[required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)、[concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)、[merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)、[least privilege](https://docs.github.com/en/actions/reference/security/secure-use)
- Release Please：[core](https://github.com/googleapis/release-please)、[Action](https://github.com/googleapis/release-please-action)、[manifest config](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md)
- OpenAI Codex：[worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)、[`AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- Anthropic Claude Code：[`CLAUDE.md`](https://code.claude.com/docs/en/memory)、[subagents](https://code.claude.com/docs/en/sub-agents)、[worktrees](https://code.claude.com/docs/en/worktrees)、[hooks](https://code.claude.com/docs/en/hooks)
- Semantic Versioning：[SemVer 2.0.0](https://semver.org/)

所有强制研究主题均找到可用的一手官方资料；没有不可用的官方主题。
