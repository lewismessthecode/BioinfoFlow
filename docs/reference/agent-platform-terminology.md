# Historical Agent Platform Terminology / 历史 Agent 平台术语

> **Superseded / 已废弃**

This page previously defined the abandoned Host/Engine, Tool Action, Decision,
Approval, Ledger, and replay-cursor architecture. Those terms are not the
current Bioinfoflow Agent domain model and must not be used as implementation
requirements.

本页原先定义了已经放弃的 Host/Engine、Tool Action、Decision、Approval、Ledger 与
replay cursor 架构。这些术语不再属于当前 Bioinfoflow Agent 领域模型，也不应继续作为
实现要求。

Use the current [Glossary](glossary.md#agent-terms) and
[Architecture Reference](architecture.md#agent-harness). The production model
is intentionally limited to:

- Agent Harness / Agent 运行框架
- Session / 会话
- Run / 一次连续工作
- History Entry / 历史条目
- Tool Call and Tool Result / 工具调用与结果
- User Interaction / 用户交互
- Context and Compaction / 上下文与压缩
- Checkpoint / 私有恢复检查点
- Workspace Runtime / 本地或远程工作区运行时

Migration mapping for old discussions:

| Historical term | Current meaning |
| --- | --- |
| Conversation | Session plus append-only History Entries |
| Turn | Run |
| Tool Action | Tool Call and its Tool Result in history |
| Decision / Approval | persisted User Interaction |
| Canonical Conversation | append-only `agent_entries` history |
| Event Ledger / Replay Cursor | authoritative snapshot plus live SSE |
| Engine / Harness Adapter | removed; there is one complete Agent Harness |
| Lease | private Run concurrency mechanism |
| Engine checkpoint | private same-version Run Checkpoint |

The historical long-form vocabulary remains available through Git history if a
migration investigation needs it. It is intentionally not reproduced here to
avoid presenting obsolete architecture as current design.
