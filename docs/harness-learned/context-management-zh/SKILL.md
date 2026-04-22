---
name: context-management-zh
description: |
  上下文窗口管理与三层压缩策略。适用于:
  (1) 实现上下文压缩(compact)、自动摘要
  (2) 设计 micro-compact 静默替换旧 tool_result
  (3) 实现 transcript 持久化与崩溃恢复
  (4) 理解 token 阈值触发与手动压缩的时机
  关键词: context, compact, 压缩, transcript, micro_compact, 上下文管理, token, 摘要, summarize
---

# 上下文管理

上下文总会满，要有办法腾地方。三层压缩策略，换来无限会话。

## 问题

上下文窗口是有限的。读一个 1000 行文件 ~4000 token; 读 30 个文件、跑 20 条命令，轻松突破 100k。不压缩，智能体没法在大项目里干活。

## 三层压缩架构

```
Every turn:
[Layer 1: micro_compact]        (静默, 每轮执行)
  超过 3 轮的旧 tool_result -> 占位符
        |
        v
[Check: tokens > 50000?]
   |               |
   no              yes
   |               |
   v               v
continue    [Layer 2: auto_compact]
              保存 transcript 到磁盘
              LLM 摘要整个对话
              替换所有 messages 为 [summary]
                    |
                    v
            [Layer 3: compact tool]
              模型显式调用 compact 工具
              触发同样的摘要机制
```

## Layer 1: Micro-Compact (每轮静默执行)

将旧的 tool_result 替换为轻量占位符:

```python
def micro_compact(messages: list) -> list:
    tool_results = []
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for j, part in enumerate(msg["content"]):
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append((i, j, part))
    if len(tool_results) <= KEEP_RECENT:
        return messages
    for _, _, part in tool_results[:-KEEP_RECENT]:
        if len(part.get("content", "")) > 100:
            part["content"] = f"[Previous: used {tool_name}]"
    return messages
```

## Layer 2: Auto-Compact (token 阈值触发)

保存完整对话到磁盘，然后 LLM 做摘要:

```python
def auto_compact(messages: list) -> list:
    # 保存 transcript 用于恢复
    transcript_path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with open(transcript_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    # LLM 摘要
    response = client.messages.create(
        model=MODEL,
        messages=[{"role": "user", "content":
            "Summarize this conversation for continuity..."
            + json.dumps(messages, default=str)[:80000]}],
        max_tokens=2000,
    )
    return [
        {"role": "user", "content": f"[Compressed]\n\n{response.content[0].text}"},
        {"role": "assistant", "content": "Understood. Continuing."},
    ]
```

## Layer 3: Manual Compact (模型主动触发)

`compact` 工具加入 dispatch map，调用同一个 `auto_compact`:

```python
TOOL_HANDLERS = {
    # ...base tools...
    "compact": lambda **kw: "COMPACT_REQUESTED",
}

# 在循环中检测
if "COMPACT_REQUESTED" in outputs:
    messages[:] = auto_compact(messages)
```

## 循环集成

```python
def agent_loop(messages: list):
    while True:
        micro_compact(messages)                        # Layer 1
        if estimate_tokens(messages) > THRESHOLD:
            messages[:] = auto_compact(messages)       # Layer 2
        response = client.messages.create(...)
        # ... 工具执行 ...
        if manual_compact_requested:
            messages[:] = auto_compact(messages)       # Layer 3
```

## 核心原则

**信息没有丢失，只是移出了活跃上下文。**

- Transcript 保存在磁盘上 (`.transcripts/`)
- 任务状态保存在 `.tasks/` (如果用了任务系统)
- 压缩后可以从磁盘重建上下文

## 最佳实践

| 策略 | 何时用 | 成本 |
|------|--------|------|
| Micro-compact | 每轮自动 | 零 (纯文本替换) |
| Auto-compact | token > 阈值 | 一次 LLM 调用 |
| Manual compact | 模型判断需要时 | 一次 LLM 调用 |
| Transcript 存盘 | 每次压缩前 | 磁盘 I/O |

1. **KEEP_RECENT = 3**: 保留最近 3 轮的 tool_result 完整内容
2. **THRESHOLD = 50000**: 根据模型上下文窗口调整
3. **摘要要保留关键信息**: 文件路径、决策、未完成的任务
4. **transcript 命名带时间戳**: 便于按时间恢复
