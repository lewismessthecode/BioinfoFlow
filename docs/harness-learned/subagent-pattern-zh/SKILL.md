---
name: subagent-pattern-zh
description: |
  子智能体上下文隔离模式。适用于:
  (1) 实现子智能体(subagent)、任务委派
  (2) 保护父上下文不被探索性任务污染
  (3) 设计子智能体的安全限制和返回策略
  (4) 判断何时用子智能体 vs 直接在主循环执行
  关键词: subagent, 子智能体, task, 上下文隔离, spawn, 委派, 独立消息, context isolation
---

# 子智能体上下文隔离

大任务拆小，每个小任务干净的上下文。子智能体用独立 messages[]，不污染主对话。

## 问题

智能体工作越久，messages 数组越胖。"这个项目用什么测试框架?" 可能要读 5 个文件，但父智能体只需要一个词: "pytest"。探索性工作的中间结果永久留在上下文里，稀释注意力。

## 架构

```
Parent agent                     Subagent
+------------------+             +------------------+
| messages=[...]   |             | messages=[]      | <-- 全新上下文
|                  |  dispatch   |                  |
| tool: task       | ----------> | while tool_use:  |
|   prompt="..."   |             |   call tools     |
|                  |  summary    |   append results |
|   result = "..." | <---------- | return last text |
+------------------+             +------------------+

父上下文保持干净。子智能体的 messages 被丢弃。
```

## 核心实现

```python
# 父智能体独有 task 工具，子智能体不能递归 spawn
PARENT_TOOLS = CHILD_TOOLS + [
    {"name": "task",
     "description": "Spawn a subagent with fresh context.",
     "input_schema": {
         "type": "object",
         "properties": {"prompt": {"type": "string"}},
         "required": ["prompt"],
     }},
]

def run_subagent(prompt: str) -> str:
    sub_messages = [{"role": "user", "content": prompt}]
    for _ in range(30):  # 安全上限
        response = client.messages.create(
            model=MODEL, system=SUBAGENT_SYSTEM,
            messages=sub_messages,
            tools=CHILD_TOOLS, max_tokens=8000,
        )
        sub_messages.append({"role": "assistant",
                             "content": response.content})
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler = TOOL_HANDLERS.get(block.name)
                output = handler(**block.input)
                results.append({"type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output)[:50000]})
        sub_messages.append({"role": "user", "content": results})
    # 仅返回最终文本摘要
    return "".join(
        b.text for b in response.content if hasattr(b, "text")
    ) or "(no summary)"
```

## 关键设计决策

### 何时用子智能体

| 场景 | 选择 | 理由 |
|------|------|------|
| 探索性搜索 (读多个文件找答案) | 子智能体 | 中间结果不需要 |
| 单步文件操作 | 主循环 | 开销不值得 |
| 代码审查/分析 | 子智能体 | 输出可能很长 |
| 编辑当前文件 | 主循环 | 需要上下文连续性 |
| 并行独立任务 | 多个子智能体 | 互不干扰 |

### 安全约束

1. **轮次上限 (30)**: 防止子智能体无限循环
2. **禁止递归 spawn**: 子智能体没有 `task` 工具
3. **输出截断**: 每个 tool_result `[:50000]`
4. **独立系统提示**: 子智能体可以有更聚焦的指令

## 最佳实践

1. **子历史即用即弃**: 30+ 次工具调用的历史，父只收到一段摘要
2. **prompt 要具体**: "找出测试框架" 比 "看看项目" 效果好
3. **不要过度使用**: 简单任务直接在主循环做
4. **子智能体是同步阻塞的**: 父等子完成后继续，不是后台运行
5. **摘要质量取决于模型**: 最后一轮的文本输出就是返回值
