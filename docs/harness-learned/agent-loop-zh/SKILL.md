---
name: agent-loop-zh
description: |
  智能体核心循环与工具分发架构。适用于:
  (1) 从零构建 AI agent、编写 agent loop
  (2) 设计工具分发(dispatch map)、添加新工具
  (3) 实现路径沙箱、输出截断等安全机制
  (4) 理解 "模型即智能体" 的核心哲学
  关键词: agent loop, 循环, dispatch map, 工具分发, safe_path, 沙箱, tool_use, stop_reason
---

# 智能体核心循环

模型已经知道如何当智能体。你的代码只需提供一个循环。

## 核心哲学

> **模型就是智能体，代码只是循环。**

智能体三要素:
- **能力 (Capabilities)**: 它能做什么 — 工具
- **知识 (Knowledge)**: 它知道什么 — 按需加载
- **上下文 (Context)**: 发生了什么 — 消息历史

## 最小循环 (~20 行)

```
+--------+      +-------+      +---------+
|  User  | ---> |  LLM  | ---> |  Tool   |
| prompt |      |       |      | execute |
+--------+      +---+---+      +----+----+
                    ^                |
                    |   tool_result  |
                    +----------------+
                    (loop until stop_reason != "tool_use")
```

```python
def agent_loop(query):
    messages = [{"role": "user", "content": query}]
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return  # 模型决定停止
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input) if handler \
                    else f"Unknown tool: {block.name}"
                results.append({"type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output)[:50000]})
        messages.append({"role": "user", "content": results})
```

后续所有机制都在这个循环上叠加，循环本身始终不变。

## Dispatch Map 模式

加工具 = 加 handler + 加 schema，循环永远不改:

```python
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}
```

一次字典查找替代所有 if/elif 链。

## 路径沙箱与输出截断

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_read(path: str, limit: int = None) -> str:
    text = safe_path(path).read_text()
    lines = text.splitlines()
    if limit and limit < len(lines):
        lines = lines[:limit]
    return "\n".join(lines)[:50000]  # 截断防爆上下文
```

## 反模式

| 模式 | 问题 | 正确做法 |
|------|------|----------|
| 过度工程 | 还没需要就加复杂度 | 从最小循环开始 |
| 工具过多 | 模型选择困难 | 3-5 个工具起步 |
| 刚性工作流 | 无法适应变化 | 让模型自己决定 |
| 前置加载知识 | 上下文膨胀 | 按需加载 |
| 微观管理 | 削弱模型智能 | 信任模型推理 |

## 最佳实践

1. **退出条件唯一**: `stop_reason != "tool_use"` 控制整个流程
2. **工具结果截断**: 所有输出 `[:50000]` 防止上下文爆炸
3. **路径沙箱**: 每个文件操作都经过 `safe_path()` 校验
4. **消息累积**: assistant 和 tool_result 都追加到同一个 messages 列表
5. **工具定义分离**: schema 和 handler 独立维护，循环不感知具体工具
