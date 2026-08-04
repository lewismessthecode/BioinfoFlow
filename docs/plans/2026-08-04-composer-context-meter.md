# Composer 上下文用量圆环

## 目标

在 Agent Composer 右下角增加一个低干扰的上下文用量圆环，让用户看到“下一次请求距离当前模型上下文上限还有多远”。圆环展示当前上下文占用率，不把 session 累计 token 误当作上下文容量；Popover 同时提供 session 累计用量、当前上下文、模型、provider、窗口来源和 compact/未知状态。

## 第一性原理与最小模型

- context window 是一次模型 API 请求可携带的容量；每轮请求由 session 历史重建当前 context。
- session cumulative usage 是流量统计，包含整个会话各次请求的 input/output/cache/reasoning token，不能用于表示当前窗口剩余空间。
- 当前上下文优先使用最近一次真实 API response 的 input usage；如果 compact 后尚未发生下一次请求，则状态为 unknown，而不是伪造 0%。
- 分母使用当前实际生效模型的 context window。模型元数据来自 provider/catalog；缺失时保持 unknown，不猜默认值。
- `cached_input_tokens` 只作为 breakdown 展示，不再次加到 canonical input tokens，避免 provider 的 input token 已包含 cache 时双算。
- 当前上下文与 session 累计永远分开存储、计算和展示；compact 可以使当前上下文下降，但累计值只增不减。

## 架构

1. Runtime 每次模型调用完成时保存 nested `last_usage`，顶层已有 usage 继续表示该 turn/session 的累计值，避免破坏历史行为。
2. Backend summary 从最新 turn 的 `last_usage` 生成 `current_context`，并返回 `source: reported | estimated | unknown`、model/provider、窗口和百分比；窗口缺失时 percentage 为 null。
3. Frontend token view model 显式建模 `currentContext` 和 `sessionTotal`，以 current context percentage 驱动圆环，以累计值驱动 Popover breakdown。
4. Composer 使用现有 Popover/i18n/Tailwind 能力实现 32–36px SVG 圆环：中心显示百分比，未知显示 `—`；70% 和 90% 复用现有 warning/critical 语义；不引入依赖或复杂动画。

## 文件范围

- 后端：`backend/app/services/agent_core/core/loop.py`、相关 schema/API summary、agent-core 测试。
- 前端：`frontend/lib/agent-runtime/types.ts`、`frontend/lib/agent-runtime/token-usage.ts`、`frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`、对应单测。
- 文案：`frontend/messages/en.json`、`frontend/messages/zh-CN.json`。

## TDD 顺序

### 1. Runtime latest usage

- 先写测试证明一个 turn 内多次模型调用时，累计 usage 与最后一次 usage 都能独立读取。
- 运行窄测试确认红灯。
- 最小修改 runtime 保存 `last_usage`，再运行测试至绿灯。
- 做一次 spec review，再做一次 code-quality review；发现问题则修复并重跑两种 review。

### 2. Backend current-context summary

- 先写测试覆盖：current context 不使用累计 total；latest usage 缺失为 unknown；窗口缺失 percentage 为 null；最新实际模型作为分母；累计 totals 保持既有行为。
- 红灯、最小实现、绿灯；随后按同样顺序 review。

### 3. Frontend view model

- 先写测试覆盖 100K current / 300K cumulative / 258K window 时显示约 39%，未知窗口不产生百分比，compact/unknown 不显示 0%，70/90 阈值保持稳定。
- 最小修改类型和 token usage selector，运行窄测试至绿灯。

### 4. Composer UI

- 先写组件测试覆盖圆环、aria label、Popover、current/cumulative 同时出现、unknown `—`、warning/critical 和 compactControls。
- 最小实现圆环及 Popover，运行组件测试至绿灯。
- 遵循 minimalist-ui 与 design-taste-frontend-v1：信息层级克制、可访问、无多余装饰。

### 5. 验证与交付

- 更新中英文文案并运行 `bun run lint:i18n`。
- 前端运行 lint、test、dead-code；后端运行 pytest、ruff check；必要时补充 diff check。
- 最终独立整体 code review。
- `git fetch origin --prune && git rebase origin/main`，解决并验证冲突。
- 推送分支、创建 PR，等待 CI/checks；通过后使用 rebase merge 合并到 `origin/main`。

## 精确验证命令

```bash
# backend/
rtk uv run pytest
rtk uv run ruff check .

# frontend/
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test

# repo root
rtk git diff --check
```

## 验收标准

- 圆环百分比只表示最近一次真实请求的当前 context / 当前模型窗口。
- session 累计 token 仍可在 Popover 中查看，且不会影响圆环百分比。
- provider/model 窗口未知时 UI 明确显示未知，不显示误导性的百分比。
- compact 后、下一次请求前显示未知；下一次请求完成后恢复真实值。
- 英文和中文文案完整，测试覆盖核心数据语义和交互。
