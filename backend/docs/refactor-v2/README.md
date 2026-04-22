# Backend Refactor V2

这套文档是对 `backend/docs/refactor/` 的重组和修订版本。目标不是重复原文，而是把现有判断整理成更适合实施的文档包。

## V2 相比 V1 的变化

1. 从“现状 + 需求 + 7 份分计划”重组为“总览 + 现状验证 + 目标架构 + 分阶段交付 + 迁移与风险”。
2. 明确区分强保证能力和 best-effort 能力，尤其是 WDL resume、资源估算、运行时 DAG 推断。
3. 补充代码层面的影响范围说明。
4. 调整 `TaskRunner` 替换策略。
   原 V1 假设可以完全删除 `runtime/task_runner.py`。
   V2 认为应只将 runs 执行链路迁移到新 scheduler，保留一个轻量后台任务器给 image pull 等非 run 任务使用。
5. 调整重构顺序。
   V2 增加一个“Phase 0: seams and characterization”阶段，先把接口边界和回归测试补齐，再拆执行链路。
6. 收紧 WDL resume 的表述。
   V1 将其视为和 Nextflow `-resume` 对等的目标。
   V2 将其定义为“应用层 restart-assist / best-effort resume”，需要单独标明语义边界。

## 阅读顺序

1. `00-overview.md`
2. `01-current-implementation.md`
3. `02-requirements-and-principles.md`
4. `03-target-architecture.md`
5. `04-phase-plan.md`
6. `05-migration-and-rollout.md`
7. `06-risks-and-open-questions.md`

## 文档定位

- `00-overview.md`
  一页结论，适合快速同步方向。
- `01-current-implementation.md`
  基于当前代码的现状梳理和问题验证。
- `02-requirements-and-principles.md`
  需求、优先级、非目标、设计原则。
- `03-target-architecture.md`
  目标模块边界、数据流、状态模型。
- `04-phase-plan.md`
  推荐实施顺序和每阶段交付目标。
- `05-migration-and-rollout.md`
  迁移方式、兼容性、上线策略、测试。
- `06-risks-and-open-questions.md`
  当前仍有不确定性的设计点和建议。

## V1 到 V2 的映射

| V1 文档 | V2 对应位置 |
|--------|-------------|
| `00-current-state.md` | `00-overview.md` + `01-current-implementation.md` |
| `01-requirements.md` | `02-requirements-and-principles.md` + `04-phase-plan.md` |
| `plan-01-engine-abstraction.md` | `03-target-architecture.md` + `04-phase-plan.md` |
| `plan-02-scheduler-core.md` | `03-target-architecture.md` + `04-phase-plan.md` + `05-migration-and-rollout.md` |
| `plan-03-resource-awareness.md` | `02-requirements-and-principles.md` + `04-phase-plan.md` + `06-risks-and-open-questions.md` |
| `plan-04-resume-retry.md` | `02-requirements-and-principles.md` + `04-phase-plan.md` + `06-risks-and-open-questions.md` |
| `plan-05-dag-compatibility.md` | `01-current-implementation.md` + `03-target-architecture.md` + `04-phase-plan.md` |
| `plan-06-monitoring-ops.md` | `04-phase-plan.md` + `05-migration-and-rollout.md` |
| `plan-07-batch-notifications.md` | `04-phase-plan.md` + `06-risks-and-open-questions.md` |

## 当前建议

如果要开始实际重构，建议先以 `04-phase-plan.md` 为主文档，再为每个 phase 生成单独 implementation plan。
