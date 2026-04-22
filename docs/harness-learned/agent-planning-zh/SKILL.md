---
name: agent-planning-zh
description: |
  智能体规划与进度追踪机制。适用于:
  (1) 实现 TodoManager、待办列表、进度管理
  (2) 设计 nag reminder 提醒机制
  (3) 多步任务中防止模型跑偏或丢失进度
  (4) 选择 Todo(内存) vs Task System(磁盘) 的场景
  关键词: todo, 规划, planning, 进度追踪, nag reminder, in_progress, TodoManager
---

# 规划与进度追踪

没有计划的智能体走哪算哪。先列步骤再动手，完成率翻倍。

## 问题

多步任务中，模型会丢失进度 — 重复做过的事、跳步、跑偏。对话越长越严重: 工具结果不断填满上下文，系统提示的影响力逐渐被稀释。

## 架构

```
+--------+      +-------+      +---------+
|  User  | ---> |  LLM  | ---> | Tools   |
| prompt |      |       |      | + todo  |
+--------+      +---+---+      +----+----+
                    ^                |
                    |   tool_result  |
                    +----------------+
                          |
              +-----------+-----------+
              | TodoManager state     |
              | [ ] task A            |
              | [>] task B  <- doing  |
              | [x] task C            |
              +-----------------------+
                          |
              if rounds_since_todo >= 3:
                inject <reminder> into tool_result
```

## TodoManager 核心实现

同一时间只允许一个 `in_progress`，强制顺序聚焦:

```python
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        validated, in_progress_count = [], 0
        for item in items:
            status = item.get("status", "pending")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({
                "id": item["id"],
                "text": item["text"],
                "status": status,
            })
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress")
        self.items = validated
        return self.render()

    def render(self) -> str:
        icons = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}
        return "\n".join(
            f"{icons[i['status']]} {i['id']}: {i['text']}"
            for i in self.items
        )
```

作为 dispatch map 中的普通工具注册:

```python
TOOL_HANDLERS = {
    # ...base tools...
    "todo": lambda **kw: TODO.update(kw["items"]),
}
```

## Nag Reminder 机制

模型连续 N 轮不更新 todo 时，在 tool_result 中注入提醒:

```python
if rounds_since_todo >= 3 and messages:
    last = messages[-1]
    if last["role"] == "user" and isinstance(last.get("content"), list):
        last["content"].insert(0, {
            "type": "text",
            "text": "<reminder>Update your todos.</reminder>",
        })
```

问责压力: 你不更新计划，系统就追着你问。

## Todo vs Task System 选择指南

| 维度 | Todo (内存) | Task System (磁盘) |
|------|-------------|---------------------|
| 持久化 | 压缩后丢失 | 重启后存活 |
| 结构 | 扁平列表 | DAG 依赖图 |
| 适用 | 单次会话内的快速清单 | 跨会话的结构化目标 |
| 复杂度 | 极低 | 中等 |
| 多 agent | 不支持 | 支持 owner 分配 |

## 最佳实践

1. **"only one in_progress" 约束**: 防止模型同时开多条线
2. **Nag 阈值 3 轮**: 太低太烦，太高失效
3. **Todo 作为普通工具**: 不需要特殊机制，dispatch map 中的一个条目
4. **渲染为文本**: `render()` 输出人类可读的清单，模型也能理解
5. **轻量场景用 Todo，重量场景用 Task**: 不要过度设计
