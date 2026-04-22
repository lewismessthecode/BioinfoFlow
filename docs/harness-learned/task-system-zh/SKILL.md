---
name: task-system-zh
description: |
  持久化任务系统与后台执行机制。适用于:
  (1) 实现任务 DAG、依赖图(blockedBy/blocks)
  (2) JSON 文件持久化任务状态
  (3) 实现后台任务执行、通知队列
  (4) 选择 Todo(内存) vs Task(磁盘) 的架构决策
  关键词: task, 任务系统, DAG, blockedBy, blocks, 后台任务, background, notification, 持久化, TaskManager
---

# 任务系统与后台执行

大目标拆成小任务，排好序，记在磁盘上。慢操作丢后台，agent 继续想下一步。

## 问题

Todo 是内存中的扁平清单: 没有依赖、压缩后丢失。真实目标是有结构的 — 任务 B 依赖 A，C 和 D 可以并行，E 要等 C 和 D 都完成。

## 任务 DAG 架构

```
.tasks/
  task_1.json  {"id":1, "status":"completed"}
  task_2.json  {"id":2, "blockedBy":[1], "status":"pending"}
  task_3.json  {"id":3, "blockedBy":[1], "status":"pending"}
  task_4.json  {"id":4, "blockedBy":[2,3], "status":"pending"}

DAG:
            +--> [task 2 pending] --+
            |                       |
[task 1 completed]            +--> [task 4 blocked]
            |                       |
            +--> [task 3 pending] --+

状态: pending -> in_progress -> completed
完成时自动解除其他任务的 blockedBy
```

## TaskManager 核心实现

```python
class TaskManager:
    def __init__(self, tasks_dir: Path):
        self.dir = tasks_dir
        self.dir.mkdir(exist_ok=True)
        self._next_id = self._max_id() + 1

    def create(self, subject, description=""):
        task = {"id": self._next_id, "subject": subject,
                "status": "pending", "blockedBy": [],
                "blocks": [], "owner": ""}
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2)

    def update(self, task_id, status=None,
               add_blocked_by=None, add_blocks=None):
        task = self._load(task_id)
        if status:
            task["status"] = status
            if status == "completed":
                self._clear_dependency(task_id)
        self._save(task)

    def _clear_dependency(self, completed_id):
        """完成时自动解锁后续任务"""
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text())
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)
```

## 后台执行机制

慢操作 (npm install, pytest) 不阻塞主循环:

```
Main thread                Background thread
+-----------------+        +-----------------+
| agent loop      |        | subprocess runs |
| [LLM call] <---+------- | enqueue(result) |
|  ^drain queue   |        +-----------------+
+-----------------+
```

```python
class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self._notification_queue = []
        self._lock = threading.Lock()

    def run(self, command: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {"status": "running", "command": command}
        thread = threading.Thread(
            target=self._execute, args=(task_id, command),
            daemon=True)
        thread.start()
        return f"Background task {task_id} started"

    def _execute(self, task_id, command):
        try:
            r = subprocess.run(command, shell=True, cwd=WORKDIR,
                capture_output=True, text=True, timeout=300)
            output = (r.stdout + r.stderr).strip()[:50000]
        except subprocess.TimeoutExpired:
            output = "Error: Timeout (300s)"
        with self._lock:
            self._notification_queue.append(
                {"task_id": task_id, "result": output[:500]})
```

每次 LLM 调用前排空通知队列:

```python
notifs = BG.drain_notifications()
if notifs:
    notif_text = "\n".join(
        f"[bg:{n['task_id']}] {n['result']}" for n in notifs)
    messages.append({"role": "user",
        "content": f"<background-results>\n{notif_text}\n"
                   f"</background-results>"})
    messages.append({"role": "assistant",
        "content": "Noted background results."})
```

## Todo vs Task 选择指南

| 维度 | Todo (s03) | Task System (s07+s08) |
|------|------------|----------------------|
| 存储 | 内存 | JSON 文件 |
| 压缩后 | 丢失 | 存活 |
| 依赖 | 无 | blockedBy/blocks DAG |
| 多 agent | 不支持 | 支持 owner |
| 后台执行 | 不支持 | daemon thread |
| 适用 | 单会话快速清单 | 跨会话结构化工作 |

## 最佳实践

1. **每个任务一个 JSON 文件**: 避免单文件锁竞争
2. **完成时自动解锁**: `_clear_dependency()` 保证 DAG 一致性
3. **通知队列线程安全**: 用 `threading.Lock` 保护
4. **drain before LLM call**: 通知在下一轮对话前注入
5. **daemon=True**: 主进程退出时后台线程自动终止
