---
name: worktree-isolation-zh
description: |
  Git worktree 双平面任务执行隔离。适用于:
  (1) 实现任务-worktree 绑定、隔离执行环境
  (2) 设计控制平面(.tasks/) + 执行平面(.worktrees/) 架构
  (3) 实现 keep vs remove 收尾策略
  (4) 事件流(events.jsonl)与崩溃恢复
  关键词: worktree, git, 隔离, isolation, 控制平面, 执行平面, events, keep, remove, 绑定, bind
---

# Git Worktree 任务隔离

各干各的目录，互不干扰。任务管目标，worktree 管目录，按 ID 绑定。

## 问题

多个智能体共享一个目录。A 改 `config.py`，B 也改 `config.py`，未提交的改动互相污染，谁也没法干净回滚。任务板管 "做什么" 但不管 "在哪做"。

## 双平面架构

```
控制平面 (.tasks/)              执行平面 (.worktrees/)
+------------------+            +------------------------+
| task_1.json      |            | auth-refactor/         |
|   status: in_progress <--->   branch: wt/auth-refactor
|   worktree: "auth-refactor"   task_id: 1             |
+------------------+            +------------------------+
| task_2.json      |            | ui-login/              |
|   status: pending   <--->     branch: wt/ui-login
|   worktree: "ui-login"        task_id: 2             |
+------------------+            +------------------------+
                                |
                      index.json (worktree 注册表)
                      events.jsonl (生命周期事件流)

状态机:
  Task:     pending -> in_progress -> completed
  Worktree: absent  -> active      -> removed | kept
```

## 生命周期

### 1. 创建任务

```python
TASKS.create("Implement auth refactor")
# -> .tasks/task_1.json  status=pending  worktree=""
```

### 2. 创建 worktree 并绑定任务

传入 `task_id` 自动将任务推进到 `in_progress`:

```python
WORKTREES.create("auth-refactor", task_id=1)
# -> git worktree add -b wt/auth-refactor .worktrees/auth-refactor HEAD
# -> index.json 新增条目, task_1.json 绑定 worktree

def bind_worktree(self, task_id, worktree):
    task = self._load(task_id)
    task["worktree"] = worktree
    if task["status"] == "pending":
        task["status"] = "in_progress"
    self._save(task)
```

### 3. 在 worktree 中执行

```python
subprocess.run(command, shell=True, cwd=worktree_path,
               capture_output=True, text=True, timeout=300)
```

### 4. 收尾: keep vs remove

```python
def remove(self, name, force=False, complete_task=False):
    wt = self._get(name)
    self._run_git(["worktree", "remove", wt["path"]])
    if complete_task and wt.get("task_id") is not None:
        self.tasks.update(wt["task_id"], status="completed")
        self.tasks.unbind_worktree(wt["task_id"])
        self.events.emit("task.completed", ...)
```

| 策略 | 何时用 | 效果 |
|------|--------|------|
| `keep` | 工作未完成，需要后续继续 | 保留目录和分支 |
| `remove` | 工作已完成或已放弃 | 删除目录，可选完成任务 |
| `remove + complete_task` | 一步到位 | 删除目录 + 标记任务完成 |

## 事件流

每个生命周期步骤写入 `.worktrees/events.jsonl`:

```json
{"event": "worktree.create.after", "worktree": {"name": "auth-refactor"}, "ts": 1730000000}
{"event": "worktree.remove.after", "task": {"id": 1, "status": "completed"}, "ts": 1730000100}
```

事件类型: `worktree.create.before/after/failed`, `worktree.remove.before/after/failed`, `worktree.keep`, `task.completed`

## 崩溃恢复

会话记忆是易失的; 磁盘状态是持久的:

- `.tasks/task_*.json` — 任务状态
- `.worktrees/index.json` — worktree 注册表
- `.worktrees/events.jsonl` — 事件审计日志

从这三个文件可以完整重建现场。

## 最佳实践

1. **先创建任务，再创建 worktree**: 控制平面先于执行平面
2. **绑定自动推进状态**: create worktree with task_id 自动 `pending -> in_progress`
3. **一个 worktree 一个分支**: `wt/` 前缀命名空间隔离
4. **事件流不可变**: append-only，用于审计和调试
5. **优先 remove + complete_task**: 一步完成拆除和状态更新
6. **index.json 是恢复的关键**: 崩溃后从 index 重建 worktree 映射
