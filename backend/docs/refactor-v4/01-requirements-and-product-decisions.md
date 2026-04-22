# Refactor-v4: Requirements and Product Decisions

## Summary

v4 的目标是把调度能力从“run 级资源感知”升级到“step 级资源调度”，并且在产品层面对不同执行引擎的能力边界做诚实表达。

第一阶段不追求 Nextflow 与 WDL 的完全统一行为，而是采用分阶段双模策略：

- `WDL`: 先落地真实的 step-level scheduling
- `Nextflow`: 暂时保留 run-level admission control

前端和 API 必须显式区分这两类模式，避免用户误以为所有 workflow 都已经支持步骤级调度。

## User Requirements

### 1. 资源调度必须从步骤维度出发

用户要求调度器能够：

- 在同一时刻考虑多个 run 的可执行步骤
- 当前资源不足以运行某个重步骤时，不阻塞其他轻量步骤
- 能让其他 run 中资源更小的步骤优先执行

换句话说，调度器目标不再是：

- “这条 run 要不要整体启动”

而是：

- “现在哪些步骤可执行，且能放进当前资源窗口”

### 2. Workflow 页面需要资源配置入口

用户已经明确指出：

- 既然后端引入了资源感知逻辑
- workflow 页面就应当能看到并维护相应配置

但 v4 里这个配置不再只是 run 级模板，而是：

- task/step 级资源声明
- engine 能力信息
- scheduling mode

### 3. 排队原因必须在 UI 中可解释

用户希望在 runs/scheduler 页面直接知道：

- 当前是在等 CPU、内存、磁盘还是 GPU
- 当前是 run 级阻塞还是 step 级阻塞
- 下次重试时间
- 当前被阻塞的是哪个 run 或哪个步骤

## Non-Goals

以下内容不在 v4 第一阶段目标内：

- 让 Nextflow 立即拥有与 WDL 完全一致的真实 step-level scheduling
- 做一个全新的独立调度产品界面替代现有 Runs / Scheduler / Workflow 页面
- 做精确的未来资源预测或历史资源建模
- 尝试把所有 engine 差异抽象到“完全看不出来”

## Product Decisions

### Decision 1: 双模策略

v4 第一阶段采用双模策略：

- `WDL = step-level scheduling`
- `Nextflow = run-level admission control`

原因：

- WDL 的 task/runtime 结构更容易被应用层接管
- Nextflow 当前虽然观测能力更强，但执行控制仍主要在 engine 进程内部

### Decision 2: UI 必须诚实表达能力边界

产品文案和页面结构必须显式告诉用户：

- 当前 workflow 是哪种调度模式
- 该模式意味着什么
- 为什么某些 workflow 能做 step 级排队，另一些只能 run 级排队

禁止使用会误导的抽象词，例如：

- “所有 workflow 都支持资源调度”
- “所有步骤都能动态排队”

除非后端真实支持。

### Decision 3: 步骤资源配置是 workflow 元数据的一部分

Workflow task 资源配置属于 workflow 结构的一部分，应保存在 workflow schema 中。

第一阶段不引入 project 级 task 资源覆盖，原因：

- 先把能力定义清楚
- 避免 project/workflow/binding 三层覆盖叠加带来复杂优先级

### Decision 4: Run 可以携带覆盖，但不破坏 workflow 默认声明

对于仍然是 run-level 的路径（尤其 Nextflow），允许 run 提交时传入资源覆盖值。

但在 product 语义上：

- workflow task resources 是默认声明
- run resources 是一次性 override

### Decision 5: 步骤级调度的“成功标准”

只有满足以下条件，才算真正实现 step-level scheduling：

1. run 创建后会生成 step 实例队列
2. 调度器领取的是 step，而不是整条 run
3. 依赖满足的轻量 step 可以先执行
4. 重步骤资源不足时，不阻塞其他 run 中的轻量 step
5. run 状态由 step 聚合得出

如果只有资源配置和展示，没有第 2-4 点，那么只能算“步骤资源元数据”，不算步骤级调度。

## UX Requirements

### Workflow 页面

- 用户能看到 workflow 当前调度模式
- 用户能查看每个 task 的资源声明
- 用户能维护 task 资源配置
- 页面能解释这些配置是否真正参与调度

### Runs 页面

- 用户能看出该 run 属于哪种调度模式
- run-level 模式下，展示 `required vs available`
- step-level 模式下，展示 step queue / blocked reason / ready steps

### Scheduler 页面

- 展示整体资源快照
- 展示 blocked runs/steps
- 区分“队列积压”和“资源不足”
- 能看出双模混跑状态

## API Requirements

后端需要至少提供以下能力：

- workflow 读写 task resources
- run 返回 scheduling_mode
- run 返回 scheduler_info
- run 可列出 steps
- scheduler 可列出 blocked items

## Backward Compatibility

v4 第一阶段必须兼容以下老数据：

- 没有 `tasks[].resources` 的 workflow
- 没有 `scheduling_mode` 的 workflow
- 只支持 run-level 的 Nextflow run

兼容原则：

- 老 workflow 默认按 engine 推导 scheduling_mode
- 老 run 在没有 step 数据时仍按现有行为返回 run-level 视图
- 前端必须以“无能力时降级展示”为默认，而不是报错

## Open Constraints Accepted for v4

本阶段接受以下现实约束：

- WDL 的真实分步执行可能需要引入新的 backend 路径，而不是继续完全依赖 `miniwdl run`
- Nextflow 暂不承诺真实 step-level dispatch
- 双模带来一定复杂度，但通过 capability 分层来控制复杂度边界
