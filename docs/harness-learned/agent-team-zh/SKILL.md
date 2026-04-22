---
name: agent-team-zh
description: |
  多智能体团队协作、通信协议与自治机制。适用于:
  (1) 实现 TeammateManager、团队名册管理
  (2) 设计 MessageBus JSONL 收件箱通信
  (3) 实现请求-响应协议(关机握手、计划审批)
  (4) 构建自治智能体: 空闲轮询、任务自动认领
  (5) 处理上下文压缩后的身份重注入
  关键词: team, 团队, teammate, MessageBus, 收件箱, inbox, protocol, 协议, 自治, autonomous, idle, claim, 身份重注入
---

# 多智能体团队协作

任务太大一个人干不完，要能分给队友。队友自己看看板，有活就认领。

## 三层演进

```
Layer 1 (团队基础): TeammateManager + MessageBus
Layer 2 (协议):     shutdown/plan 请求-响应 FSM
Layer 3 (自治):     IDLE 轮询 + 任务自动认领 + 身份重注入
```

## Layer 1: 团队基础设施

### TeammateManager

通过 config.json 维护团队名册，每个队友一个线程:

```python
class TeammateManager:
    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.config = self._load_config()  # config.json
        self.threads = {}

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = {"name": name, "role": role, "status": "working"}
        self.config["members"].append(member)
        self._save_config()
        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt), daemon=True)
        thread.start()
        return f"Spawned '{name}' (role: {role})"
```

### MessageBus

Append-only JSONL 收件箱。`send()` 追加一行; `read_inbox()` 读取并清空:

```python
class MessageBus:
    def send(self, sender, to, content, msg_type="message"):
        msg = {"type": msg_type, "from": sender,
               "content": content, "timestamp": time.time()}
        with open(self.dir / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg) + "\n")

    def read_inbox(self, name):
        path = self.dir / f"{name}.jsonl"
        if not path.exists():
            return "[]"
        msgs = [json.loads(l) for l in
                path.read_text().strip().splitlines() if l]
        path.write_text("")  # drain
        return json.dumps(msgs, indent=2)
```

```
.team/
  config.json           <- 团队名册 + 状态
  inbox/
    alice.jsonl         <- append-only, drain-on-read
    bob.jsonl
    lead.jsonl
```

## Layer 2: 协议 FSM

一个 FSM 驱动所有协商: `pending -> approved | rejected`

```
Shutdown Protocol            Plan Approval Protocol
Lead --shutdown_req--> Teammate   Teammate --plan_req--> Lead
     <--shutdown_resp--                   <--plan_resp--
     {req_id, approve: bool}             {req_id, approve: bool}
```

```python
shutdown_requests = {}

def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down gracefully.",
             "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent"
```

同一个 `pending -> approved | rejected` 状态机可以套用到任何请求-响应协议。

## Layer 3: 自治机制

队友自己扫描任务看板，有活就认领:

```
+-------+   tool_use    +-------+
| WORK  | <------------ |  LLM  |
+---+---+               +-------+
    |
    | stop_reason != tool_use
    v
+--------+
|  IDLE  |  poll every 5s, up to 60s
+---+----+
    +---> check inbox --> message? ------> WORK
    +---> scan .tasks/ --> unclaimed? ---> claim -> WORK
    +---> 60s timeout ------------------> SHUTDOWN
```

```python
def _idle_poll(self, name, messages):
    for _ in range(IDLE_TIMEOUT // POLL_INTERVAL):
        time.sleep(POLL_INTERVAL)
        inbox = BUS.read_inbox(name)
        if inbox:
            messages.append({"role": "user",
                "content": f"<inbox>{inbox}</inbox>"})
            return True
        unclaimed = scan_unclaimed_tasks()
        if unclaimed:
            claim_task(unclaimed[0]["id"], name)
            messages.append({"role": "user",
                "content": f"<auto-claimed>Task #{unclaimed[0]['id']}: "
                           f"{unclaimed[0]['subject']}</auto-claimed>"})
            return True
    return False  # timeout -> shutdown
```

### 身份重注入

上下文压缩后，智能体可能忘了自己是谁:

```python
if len(messages) <= 3:  # 压缩发生的信号
    messages.insert(0, {"role": "user",
        "content": f"<identity>You are '{name}', role: {role}, "
                   f"team: {team_name}. Continue your work.</identity>"})
    messages.insert(1, {"role": "assistant",
        "content": f"I am {name}. Continuing."})
```

## 最佳实践

1. **JSONL append-only**: 写入不需要锁，读取时原子清空
2. **drain-on-read**: 读收件箱 = 消费消息，防止重复处理
3. **每轮检查收件箱**: 在 LLM 调用前注入新消息
4. **daemon=True**: 队友线程跟随主进程退出
5. **60 秒空闲超时**: 没有工作时自动关机，不浪费资源
6. **身份在压缩后重注入**: `len(messages) <= 3` 是压缩发生的信号
