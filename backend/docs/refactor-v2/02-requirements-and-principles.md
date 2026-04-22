# 02 — 修订后的需求与设计原则

本文件保留 V1 的需求主线，但根据代码现状调整了优先级和表述方式。

## 决策前提

### 保持不变

1. 双引擎继续保留。
   Nextflow 为主，WDL 为辅。
2. 执行环境仍以本地单机为起点。
3. 保持 FastAPI + SQLAlchemy + SQLite 单体架构。
4. 保持 REST response envelope 和 SSE 事件兼容。
5. 不引入 Redis、RabbitMQ、Celery、Cromwell。

### V2 新增的显式前提

1. V2 scheduler 的运行前提是单进程单实例。
   SQLite 方案在这个前提下是成立的，但不是为多实例调度设计。
2. WDL resume 在 V2 中不定义为强保证能力。
3. 资源感知是“减少资源超卖”，不是“精确调度”。
4. webhook 通知在 V2 中仅保证尽力发送，不保证持久投递。

## 非目标

以下内容不属于本轮重构范围：

1. Agent 自动编排多个 workflow。
2. 可视化 DAG 编辑器。
3. 多实例调度和分布式锁。
4. 远程执行后端的完整实现。
5. 对所有 pipeline 做精确资源画像。

## 修订后的需求矩阵

| ID | 主题 | V2 优先级 | V2 说明 |
|----|------|-----------|---------|
| R1 | 引擎抽象层 | P0 | 必做，所有后续能力的基础 |
| R2 | 持久化 run scheduler | P0 | 必做，替换 run 执行链路中的内存队列 |
| R3 | 资源感知调度 | P1 | 在 scheduler 稳定后做，先做保守版 |
| R4 | resume + retry | P0/P1 | Nextflow resume 和平台级 retry 为 P0；WDL resume 为 P1 best-effort |
| R5 | DAG 兼容性 | P1 | 在执行链路稳定后推进 |
| R6 | 监控与运维 | P0/P1 | timeout 为 P0；cleanup/audit 为 P1 |
| R7 | 批量投递 + 通知 | P2 | 明显依赖前述基础设施 |

## 能力分类: 强保证 vs best-effort

### 强保证能力

这些能力在文档、代码、API 语义上都应有稳定定义。

1. run create / cancel / retry / resume 的状态转换合法性
2. 持久化队列中的 queued task 不因进程重启直接丢失
3. Nextflow resume 的 token 解析和重提交流程
4. timeout 到期后的自动 cancel
5. 现有 SSE envelope 和 API 响应兼容

### Best-effort 能力

这些能力允许在文档中写清楚限制条件，不应过度承诺。

1. WDL resume
2. 资源估算与资源模板映射
3. 运行时 DAG 动态补全
4. webhook 通知交付
5. OOM 自动扩容重试

## 设计原则

### 1. 服务层不要再知道引擎细节

`RunService` 的职责应收敛为：

- 参数验证
- run 记录创建
- 入队 / 取消 / 查询
- 用户侧 API 语义

它不应该再知道：

- Nextflow 和 WDL 的命令行差异
- Docker profile 注入方式
- 子进程事件解析细节

### 2. 调度与执行分层

应区分：

- 调度: 谁先执行、何时执行、重试与恢复
- 执行: 如何启动进程、如何取消、如何解析事件

### 3. 对 `Run.config` 做“先收口，后拆分”

V2 建议：

1. 保留 `Run.config` 作为兼容字段
2. 建立明确命名空间
3. 引入 `config_schema_version`
4. 通过 helper 访问，而不是在各处自由拼装 dict

建议命名空间：

```json
{
  "config_schema_version": 1,
  "request": {
    "params": {},
    "inputs": {},
    "config_overrides": {}
  },
  "resolved": {
    "runspec": {}
  },
  "runtime": {
    "engine": "",
    "pid": null,
    "resume_token": null,
    "artifacts": {}
  },
  "policy": {
    "retry": {},
    "timeout_seconds": null
  },
  "ui": {
    "dag": {}
  }
}
```

这不要求第一阶段就完成完全迁移，但必须成为后续阶段的约束。

### 4. 新能力默认以兼容现有前端为前提

可以新增事件类型，但不应破坏：

- `/runs` 相关现有响应
- `run.status`
- `run.log`
- `run.dag`

### 5. 每个阶段都应有独立可验收价值

不要把所有改动合成一次大迁移。每个 phase 都应能独立合并并稳定运行。

## 修订后的验收思路

### P0 阶段应达成

1. run 执行链路不再依赖内存 FIFO 队列
2. Nextflow / WDL 共享统一 adapter 接口
3. 支持平台级 retry 基线
4. 支持 timeout 基线

### P1 阶段应达成

1. DAG/schema 能力明显改善
2. 资源感知调度有保守版实现
3. cleanup 和 audit 能覆盖主要运维场景
4. WDL best-effort resume 有明确限制并有测试

### P2 阶段应达成

1. 批量投递 API
2. 批次状态聚合
3. webhook 通知

## 对原需求的关键修订

### 修订 1: WDL resume 降级为 P1 best-effort

原因：

- 当前代码没有引擎原生 resume
- subworkflow、call caching、task output reuse 的语义复杂
- 如果在 P0 承诺“WDL 续跑已完成”，后续实现很容易与用户预期不一致

### 修订 2: 先做 timeout，再做完整 ops 套件

timeout 直接降低 run 永久挂起风险，应提前。
cleanup、审计、磁盘管理可以随后进入同一阶段或下一阶段。

### 修订 3: 先把 run scheduler 独立出来，再谈“完全替换 TaskRunner”

原因：

- image pull 仍然需要通用后台执行能力
- run scheduler 和 generic background tasks 的要求不同
