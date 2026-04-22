# 06 — 风险、限制与待决问题

本文件记录 V2 仍然存在的不确定点，避免在实施时把假设误写成事实。

## 一、需要明确写入文档的限制

### 1. WDL resume 不是 Nextflow resume 的等价物

建议文档统一表述为：

- Nextflow: native resume
- WDL: best-effort restart assist

如果后续实现只是复用 work dir 和记录已完成 task，就必须在 API 和文档里避免使用“保证断点续跑”这种表述。

### 2. SQLite scheduler 默认只面向单实例

V2 的 DB-backed scheduler 可以在单进程单实例内稳定工作，但不是多实例调度方案。

如果未来要支持：

- 多个 API 进程
- 多个 worker 实例
- 多机执行

则需要重新设计 dequeue 锁和 leader/worker 协调。

### 3. 资源感知只能先做保守版

资源模板和 pipeline 名称映射本身就带有经验性。

V2 应把目标定义为：

- 避免明显资源超卖
- 给出运维可见性

而不是：

- 精确预测每个任务资源曲线

### 4. webhook 不做 durable delivery

如果 webhook 发送失败，V2 建议：

- 记录日志
- 可选记录审计或通知历史

但不要求消息持久化重投递队列。

## 二、技术风险

### 风险 1: `Run.config` 继续无序增长

即便引入新 scheduler，如果不先把 `Run.config` 的结构收口，后续：

- retry
- timeout
- cleanup
- dag
- runtime metadata

仍然会继续互相污染。

建议：

- Phase 0 就建立命名空间和 helper

### 风险 2: DAG 动态构建可能误导用户

当 schema 不完整、只能依赖运行时事件推断 DAG 时，图不一定代表完整真实依赖关系。

建议：

- 在内部区分 schema DAG 和 runtime DAG
- 前端如有需要，可在 metadata 中标识 DAG 来源

### 风险 3: 自动 cleanup 可能和调试需求冲突

成功后自动清理 work-dir 是合理的，但失败后往往需要保留现场。

建议默认策略：

- 成功可清
- 失败保留
- 支持手动 cleanup

### 风险 4: OOM 自动重试容易掩盖配置问题

OOM 自动加资源后重试虽然对生信场景有吸引力，但也可能掩盖 workflow 本身配置错误。

建议：

- 初期只识别常见 OOM 模式
- 增加明确日志
- 不做无限升级

## 三、待决问题

### Q1. `Run.config` 是否需要在 V2 内拆表

建议答案：

- 不需要在 V2 早期拆表
- 先做 schema version 和 access helper
- 等 scheduler、retry、timeout 稳定后再评估

### Q2. 是否把 image pull 纳入统一 scheduler

建议答案：

- 不纳入 V2 的 run scheduler
- 保持 generic background runner

理由：

- 任务模型不同
- 状态机不同
- 实施成本高于收益

### Q3. WDL resume 的最小可交付语义是什么

建议答案：

最小可交付应定义为：

1. 保留 work dir
2. 记录已知完成任务
3. 重提交流程时尽量复用已有中间产物

不应默认承诺：

1. 所有 subworkflow 都能正确跳过
2. 所有 call caching 都与用户预期一致

### Q4. DAG 是否应该拆成独立持久化对象

建议答案：

- V2 不强制拆
- 继续存在 `Run.config.ui.dag`
- 但增加大小和写入频率方面的观察

### Q5. 是否需要在 V2 就实现 SSHBackend / CloudBackend

建议答案：

- 不需要
- 只保留 interface 即可

## 四、推荐决策

如果需要现在就定调，建议采用以下决策：

1. 只对 runs 引入专用 scheduler
2. 先做 engine abstraction，再做持久化 run scheduler
3. 将 timeout 提前到 retry/ops baseline 阶段
4. 将 WDL resume 定义为 P1 best-effort
5. 资源感知和 batch 都放在基础设施稳定之后

## 五、开始实施前应确认的事项

1. 是否接受单实例 scheduler 前提
2. 是否接受 WDL resume 的 best-effort 定义
3. 是否接受 `Run.config` 在 V2 内只做结构收口、不立即拆表
4. 是否接受 image pull 不纳入 run scheduler

这些问题如果先对齐，后面的 implementation plan 会清晰很多。
