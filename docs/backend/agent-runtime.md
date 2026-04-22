# Backend Agent Runtime

## Default Runtime Path

Production chat goes through runtime v2:

1. `AgentService.send_message()` validates the project and resolves or creates the conversation.
2. The user message is persisted to `messages`.
3. `SessionState` is built with the project/conversation IDs and optional workspace root.
4. Runtime helpers are created:
   - `SkillLoader` for `agent-skills/`
   - `TaskManager` for persistent task state when a workspace exists
   - `BackgroundManager` for long-running shell work
   - `TodoManager` inside session state
   - unified dispatch map from runtime tools, registry tools, and compatibility tools
5. Prior conversation history is loaded into the session state.
6. `agent_loop()` runs the async LLM/tool loop with a dynamic system prompt and cancellation hook.
7. Every emitted event is persisted as a `messages` row and then published over SSE.
8. Terminal state emits `agent.done` or `agent.cancelled`.

## Runtime v2 Modules

Key modules under `backend/app/services/agent/runtime/`:

- `loop.py`: core async agent loop
- `dispatch.py`: unified tool registry for the loop
- `llm_client.py`: provider abstraction for Anthropic, OpenAI, Gemini, and tests
- `session_state.py`: per-conversation mutable runtime state
- `system_prompt.py`: dynamic system prompt composition
- `compact.py`: micro/auto/manual context compaction
- `todo.py`: in-session todo management
- `tasks.py`: persistent task DAG/state in workspace context
- `background.py`: long-running shell command management
- `skills.py`: skill loading and description injection
- `subagent.py`: child-agent execution
- `messages.py`: plain-dict message helpers

## Tooling Layers

Runtime v2 can dispatch:

- registry tools built on `BaseTool`
- workflow/file/search/code tools
- runtime-native tools such as todo/task/background helpers
- compatibility/legacy agent tools where needed

The runtime registers some tools dynamically after session setup, so the final dispatch map depends on workspace availability and current session state.

## Event Mapping

Persisted message type -> SSE event:

- `thinking` -> `agent.thinking`
- `plan` -> `agent.plan`
- `artifact` -> `agent.artifact`
- `text`, `status`, `completion` -> `agent.message`

The service additionally emits:

- `agent.done`
- `agent.cancelled`

Frontend code consumes these through `use-events` and transforms them in `frontend/lib/chat-utils.ts`.

## Persistence And Observability

- Conversation history is stored in `conversations` and `messages`.
- Trace events can be written to `agent_traces` when `agent_observability=true`.
- Conversation runtime registration/cancellation is tracked through `conversation_manager`.
- The current runtime rehydrates prior messages into each session before continuing the conversation.

## Approval Status

- Approval models, repository/service logic, and API endpoints are implemented.
- Conversations carry a `policy_mode`.
- The default runtime path does not yet stop on pending approvals before executing risky actions, so approvals are a present subsystem rather than an enforced default policy gate.
