# Agent Harness Upgrade: Bioinformatics Claude Code

**Date:** 2026-04-02
**Status:** Draft → Approved
**Scope:** Unified spec covering LLM providers, agent tools, event system, and thinking UI

## Summary

Upgrade bioinfoflow's agent from a domain-specific tool-caller to a "bioinformatics Claude Code" — a general-purpose agentic assistant with modern LLM support, lean tooling, and a polished thinking UI.

Three interconnected subsystems:
1. **LLM Provider Architecture** — drop LangChain, use official SDKs, add 5 providers with extended thinking
2. **Agent Tool Refactor** — remove 6 over-wrapped tools, add 3 new primitives, lean down to ~21 tools
3. **Thinking Block UI** — Claude-style collapsible container with real reasoning text + tool pills

---

## 1. LLM Provider Architecture

### 1.1 Design Principle: Official SDKs Only

**Drop LangChain entirely.** The project doesn't use LangSmith, LangGraph, or any LangChain chains/agents. LangChain adds abstraction overhead and delays access to provider-specific features (extended thinking, reasoning effort, thought signatures).

**3 SDK dependencies → 5 providers:**

| Provider | SDK | Base URL | Auth |
|----------|-----|----------|------|
| Anthropic | `anthropic` (AsyncAnthropic) | default | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` (AsyncOpenAI) | default | `OPENAI_API_KEY` |
| Gemini | `google-genai` (genai.Client) | default | `GEMINI_API_KEY` |
| OpenRouter | `openai` (AsyncOpenAI) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Ollama | `openai` (AsyncOpenAI) | `http://localhost:11434/v1` | none |

OpenRouter and Ollama both expose OpenAI-compatible endpoints, so one SDK handles three providers.

### 1.2 Provider Registry

```python
# backend/app/services/agent/runtime/providers.py

PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        sdk="anthropic",
        default_model="claude-sonnet-4-6",
        thinking_param="budget_tokens",
        models=["claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5"],
    ),
    "openai": ProviderConfig(
        sdk="openai",
        default_model="gpt-5.4",
        thinking_param="reasoning_effort",
        models=["gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini"],
    ),
    "gemini": ProviderConfig(
        sdk="google-genai",
        default_model="gemini-3.1-pro-preview",
        thinking_param="thinking_level",
        models=["gemini-3.1-pro-preview", "gemini-3.1-flash"],
    ),
    "openrouter": ProviderConfig(
        sdk="openai",
        default_model="anthropic/claude-sonnet-4-6",
        thinking_param="reasoning_effort",  # OpenRouter passes through
        base_url="https://openrouter.ai/api/v1",
        models=[],  # any model via OpenRouter catalog
    ),
    "ollama": ProviderConfig(
        sdk="openai",
        default_model="llama3.3",
        thinking_param=None,  # most local models don't support thinking
        base_url="http://localhost:11434/v1",
        models=[],  # user-pulled models
    ),
}
```

### 1.3 Extended Thinking Integration

Each provider exposes thinking differently:

| Provider | API Parameter | Values | Response Field |
|----------|--------------|--------|----------------|
| Anthropic | `thinking={type:"enabled", budget_tokens:N}` | 1000–100000 | `block.type=="thinking"`, `block.thinking` |
| OpenAI | `reasoning={effort:"high"}` | "none","low","medium","high","xhigh" | reasoning tokens (not exposed as text) |
| Gemini | `thinking_config={thinking_level:"high"}` | "low","medium","high" | thought signatures (encrypted) |
| OpenRouter | pass-through of underlying provider | varies | varies |
| Ollama | N/A | N/A | N/A |

**Key insight:** Only Anthropic currently returns readable thinking text. OpenAI and Gemini expose reasoning tokens for billing but don't return the reasoning text itself. The `thinking_content` event will contain real text for Anthropic models and be empty for others (graceful degradation — the thinking UI shows tool traces as fallback).

### 1.3.1 Streaming Requirement (Codex Finding #1)

The current `LLMClient.create()` is **request/response only** — it blocks until the full response returns. To stream thinking text in real-time, we need a new `LLMClient.stream()` method:

```python
async def stream(
    self,
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    on_text: Callable[[str], Awaitable[None]] | None = None,
) -> LLMResponse:
    """Stream response, emitting thinking/text deltas via callbacks.
    
    Returns the complete LLMResponse after streaming finishes.
    For Anthropic: uses client.messages.stream() context manager.
    For OpenAI: uses client.chat.completions.create(stream=True).
    For Gemini: uses generate_content(stream=True).
    """
```

The agent loop calls `llm.stream()` instead of `llm.create()`, passing `on_thinking` and `on_text` callbacks that emit SSE events as deltas arrive. The `llm.create()` method remains for backward compatibility (tests, subagent calls).

**Phase 1 scope note:** Streaming is the most complex part of the LLM refactor. If it risks delaying the whole project, we can ship thinking as a **single complete event** (emitted after `llm.create()` returns the full thinking text) as an interim step, and add true streaming in a follow-up.

### 1.4 LLMResponse Changes

```python
@dataclass(frozen=True)
class LLMResponse:
    content: list[dict[str, Any]]     # ContentBlock dicts (text, tool_use)
    stop_reason: str                   # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int]             # input_tokens, output_tokens
    thinking: str | None = None        # NEW: reasoning text (Anthropic only for now)
    thinking_tokens: int = 0           # NEW: thinking token count for all providers
```

### 1.5 Config Changes

```python
# New settings in config.py
openrouter_api_key: str = ""
openrouter_model: str = ""
ollama_base_url: str = "http://localhost:11434"
ollama_model: str = ""
agent_thinking_enabled: bool = True
agent_thinking_budget: int = 10000      # Anthropic budget_tokens
agent_thinking_effort: str = "medium"   # OpenAI reasoning effort
agent_thinking_level: str = "medium"    # Gemini thinking level
```

### 1.6 Files to Change

| File | Action |
|------|--------|
| `backend/app/services/agent/runtime/llm_client.py` | Major refactor — add `_call_openai_native()`, `_call_gemini_native()`, `_build_openrouter_client()`, `_build_ollama_client()`, `stream()` method. Remove `_call_langchain()`. Add thinking extraction. |
| `backend/app/services/agent/runtime/providers.py` | NEW — provider registry with `ProviderConfig` dataclass |
| `backend/app/services/agent/llm_providers.py` | DELETE — replaced by providers.py + llm_client.py |
| `backend/app/services/agent/graph.py` | DELETE — v1 LangGraph agent, depends on LangChain |
| `backend/app/services/agent/agent_service.py` | Remove v1 `_run_v1_graph()` path and `agent_runtime_v2` conditional. Remove `graph.py` import. |
| `backend/app/config.py` | Add new settings (openrouter, ollama, thinking). Remove `agent_runtime_v2` flag. |
| `backend/pyproject.toml` | Remove `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-core`, `langgraph`. Add `google-genai`. Keep `anthropic`, `openai`. |
| `backend/app/models/user_settings.py` | Add `openrouter_api_key`, `ollama_base_url`, `ollama_model` columns |
| `backend/app/schemas/user_settings.py` | Add OpenRouter/Ollama fields to `UserSettingsRead` and `UserSettingsUpdate` |
| `backend/app/services/user_settings_service.py` | Handle new provider fields in settings service |
| `frontend/hooks/use-llm-settings.ts` | Add OpenRouter/Ollama to provider options and settings UI |

**Ordering constraint (Codex Finding #3):** Delete `graph.py` and remove the v1 routing path from `agent_service.py` BEFORE removing LangChain dependencies from `pyproject.toml`. Otherwise imports break.

### 1.7 Model Inference

Update `_infer_provider_from_model()`:

```python
def _infer_provider_from_model(model: str) -> str:
    m = model.lower()
    # IMPORTANT: Check "/" FIRST — OpenRouter models use "provider/model" format
    # e.g., "anthropic/claude-sonnet-4-6" must resolve to openrouter, not anthropic.
    # (Codex Finding #2: previous order matched "claude" before "/" → wrong provider)
    if "/" in m: return "openrouter"
    if "claude" in m: return "anthropic"
    if "gpt" in m or "o1" in m or "o3" in m: return "openai"
    if "gemini" in m: return "gemini"
    return "ollama"  # fallback: assume local model
```

---

## 2. Agent Tool Refactor

### 2.1 Design Principle: Lean Primitives

The agent already has `safe_shell` which allows common CLI commands. Domain-specific operations (git, API calls, Docker) should be taught via system prompt instructions, not wrapped as dedicated tools. Only create tools where there's a **structural advantage** over shell execution:

- **Permission-aware path validation** (file tools, glob, grep)
- **Structured output** (glob returns file lists, grep returns matches with context)
- **Result size management** (spill large results to file)
- **No shell equivalent** (web_search)

### 2.2 Tools to Remove or Refactor

| Tool | Action | Rationale |
|------|--------|-----------|
| `scan_dir` | **Remove** — replaced by `glob` | `glob` is strictly more capable. Bioinformatics file type knowledge moves to system prompt. |
| `visualize_result` | **Remove** — replaced by `file_read` | Duplicate functionality (reads file head). |
| `search_workflows` | **Keep as thin inline handler** | Calls `WorkflowRepository` directly, returns structured JSON. 5-line function in `dispatch.py`. |
| `list_images` | **Keep as thin inline handler** | Calls `ImageRepository` directly, project-scoped. |
| `read_logs` | **Keep as thin inline handler** | Calls `RunService` directly, returns structured logs. |
| `validate_workflow` | **Keep as thin inline handler** | Calls validation service, returns structured result. |

**Why keep 4 as inline handlers instead of CLI calls (Codex Finding #6):** These tools call internal services with project scoping and return structured data. Replacing with `bif` CLI calls would be a regression — the CLI requires a running server, `bif` may not be on PATH in the server runtime, and output would be unstructured text. The thin-wrapper approach preserves correctness while deleting the `legacy_tools.py` class.

### 2.3 Tools to Add

#### `glob` (replaces `scan_dir`)

```python
class GlobTool(BaseTool):
    name = "glob"
    risk_level = RiskLevel.READ
    description = "Find files matching a glob pattern. Returns sorted file paths."

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.fastq.gz', 'data/*.bam')"},
            "path": {"type": "string", "description": "Base directory (default: workspace root)"},
        },
        "required": ["pattern"],
    }
```

Implementation: `pathlib.Path(base).glob(pattern)`, workspace-scoped, sorted by mtime.

#### `grep` (replaces `code_search`)

```python
class GrepTool(BaseTool):
    name = "grep"
    risk_level = RiskLevel.READ
    description = "Search file contents using regex. Returns matching lines with context."

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "File or directory to search in"},
            "glob": {"type": "string", "description": "File filter (e.g., '*.py', '*.wdl')"},
            "context": {"type": "integer", "description": "Lines of context around matches (default: 2)"},
            "case_insensitive": {"type": "boolean", "description": "Case-insensitive search"},
        },
        "required": ["pattern"],
    }
```

Implementation: Wraps `rg` (ripgrep) subprocess if available, falls back to Python `re` module. Result size limit with spill-to-file.

#### `web_search`

```python
class WebSearchTool(BaseTool):
    name = "web_search"
    risk_level = RiskLevel.READ
    description = "Search the web. Returns titles, snippets, and URLs."

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default: 5)"},
        },
        "required": ["query"],
    }
```

Implementation: Uses `duckduckgo-search` package (no API key needed).

### 2.4 Tool Rename

- `code_search` → **removed** (replaced by `grep` which is more general-purpose)

### 2.5 Expand `safe_shell` → New `ShellTool` BaseTool

The current `safe_shell` has critical limitations (Codex Findings #4, #5):
- **10-second timeout** — too short for `docker pull`, `bif run logs`, large `git diff`
- **4K char output limit** — too small for useful CLI output
- **Risk levels are metadata-only** — the v2 loop does NOT enforce them before executing tools

The new `ShellTool` must fix all three:

```python
class ShellTool(BaseTool):
    name = "safe_shell"  # keep name for backward compatibility
    risk_level = RiskLevel.ACT_LOW
    
    # Per-command risk classification
    READ_COMMANDS = {
        "ls", "pwd", "cat", "head", "tail", "wc", "rg", "find",
        "grep", "tree", "du", "file", "stat", "zcat", "zless", "gunzip",
    }
    WRITE_COMMANDS = {
        "bif", "git", "docker", "curl", "wget", "python", "pip", "uv",
    }
    BLOCKED_COMMANDS = {
        "rm", "mv", "chmod", "chown", "kill", "pkill", "sudo", "su",
        "shutdown", "reboot", "mkfs", "dd", "format",
    }
    
    # Fix #5: Increase limits
    TIMEOUT_SECONDS = 120    # was 10 — docker pull can take minutes
    MAX_OUTPUT_CHARS = 50000  # was 4000 — match dispatch.py MAX_TOOL_OUTPUT_CHARS
```

**Risk enforcement in the loop (Codex Finding #4):** The agent loop (`loop.py`) must add a permission check before tool execution. For now, a simple approach:
- `RiskLevel.READ` → execute immediately
- `RiskLevel.ACT_LOW` → execute, but log to trace recorder
- `RiskLevel.ACT_HIGH` → require user approval (emit `agent.approval_required` event, wait for confirmation)

This is a new section in `loop.py` that wraps the existing `_dispatch_tool_call()` function.

### 2.5.1 Service-Backed Tools: Thin Wrappers vs Shell (Codex Finding #6)

Codex correctly flagged that replacing service-backed tools (like `search_workflows`) with `bif` CLI calls is a regression — current tools hit internal services with project scoping and return structured data.

**Revised approach:** For the 6 tools being removed:
- `scan_dir` → **replaced by `glob`** (this is a real improvement, not a regression)
- `visualize_result` → **replaced by `file_read`** (equivalent functionality)
- `search_workflows`, `list_images`, `read_logs` → **keep as thin service wrappers** (5-line async functions in dispatch.py that call the repository layer directly, not CLI). Move from `legacy_tools.py` to inline registration in `dispatch.py`.
- `validate_workflow` → **keep as thin wrapper** calling the existing validation service

This preserves structured data and project scoping while still deleting the `legacy_tools.py` class. The tools become lean inline handlers, not heavyweight class methods.

### 2.6 System Prompt Enhancements

Move domain-specific knowledge from tools to system prompt:

```
## Bioinformatics CLI

Use `safe_shell` to run `bif` CLI commands for domain operations:

- `bif workflow list` — list available pipelines
- `bif workflow search "variant calling"` — search workflows
- `bif workflow validate <id>` — validate workflow config
- `bif image list` — list container images
- `bif image pull <name>` — pull container image
- `bif run list` — list pipeline runs
- `bif run logs <id>` — read run logs
- `bif project list` — list projects

## File Types

When searching bioinformatics data, look for:
- Sequences: .fastq, .fastq.gz, .fasta, .fa, .fq
- Alignments: .bam, .sam, .cram, .bai
- Variants: .vcf, .vcf.gz, .bcf, .tbi
- Annotations: .gff, .gtf, .bed
- Configs: .wdl, .nf (workflow definitions)

## Git

Use `safe_shell` for git operations:
- `git status`, `git diff`, `git log --oneline -20`
- `git add <file>`, `git commit -m "message"`
```

### 2.8 Final Tool Count

| Category | Tools | Count |
|----------|-------|-------|
| File ops | file_read, file_write, file_edit | 3 |
| Search | glob, grep | 2 |
| Execution | execute_code, safe_shell, run_workflow | 3 |
| Domain (inline) | search_workflows, list_images, read_logs, validate_workflow | 4 |
| Web | web_search | 1 |
| Session | todo_write, compact, load_skill | 3 |
| Tasks | task_create, task_update, task_get, task_list | 4 |
| Background | background_run | 1 |
| Delegation | task (subagent) | 1 |
| **Total** | | **22** |

Down from ~25 to 22. Removed 2 (scan_dir, visualize_result), added 3 (glob, grep, web_search), kept 4 domain tools as thin inline handlers. The real win is eliminating the `LegacyAgentTools` class and unifying everything under BaseTool + inline dispatch.

### 2.9 Files to Change

| File | Action |
|------|--------|
| `backend/app/services/agent/tools/search_tools.py` | Refactor: rename `code_search` → `grep`, add regex support, context lines, glob filter |
| `backend/app/services/agent/tools/file_tools.py` | Add `GlobTool` class |
| `backend/app/services/agent/tools/web_tools.py` | NEW — `WebSearchTool` |
| `backend/app/services/agent/tools/shell_tool.py` | NEW — `ShellTool` extracted from legacy, with expanded commands, 120s timeout, 50K char limit, per-command risk classification |
| `backend/app/services/agent/tools/workflow_tools.py` | DELETE — replaced by inline handlers in dispatch.py |
| `backend/app/services/agent/tools/legacy_tools.py` | DELETE — `LegacyAgentTools` class removed. `safe_shell` → `ShellTool`. Domain tools → inline dispatch handlers. |
| `backend/app/services/agent/runtime/dispatch.py` | Major refactor — remove `_register_legacy_tools()`, register new BaseTool instances, add inline handlers for `search_workflows`/`list_images`/`read_logs`/`validate_workflow` |
| `backend/app/services/agent/runtime/loop.py` | Add risk-level enforcement before tool execution |
| `backend/app/services/agent/runtime/system_prompt.py` | Add bioinformatics CLI guide, file types, git instructions. Remove references to deleted tools. |
| `backend/app/services/agent/runtime/llm_client.py` | Update `DeterministicTestClient` to emit `glob` instead of `scan_dir` |

---

## 3. Event System Upgrade

### 3.1 Extended Event Envelope

Backward-compatible additions to the SSE event data:

```python
# SSE event data structure
data = {
    "id": message_id,           # DB message ID (existing)
    "type": message_type,       # MessageType value (existing)
    "content": content,         # text body (existing)
    "metadata": metadata,       # structured data (existing)
    "timestamp": iso_timestamp, # NEW: ISO 8601
    "sequence": seq_number,     # NEW: monotonic counter per turn
    "stream": is_delta,         # NEW: true = incremental delta
}
```

### 3.2 New Message Type

```python
class MessageType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"                    # tool trace events (existing)
    THINKING_CONTENT = "thinking_content"    # NEW: model reasoning text
    ARTIFACT = "artifact"
    PLAN = "plan"
    STATUS = "status"
    COMPLETION = "completion"
```

### 3.3 Event Map Update

```python
EVENT_MAP = {
    MessageType.THINKING.value: "agent.thinking",
    MessageType.THINKING_CONTENT.value: "agent.thinking_content",  # NEW
    MessageType.PLAN.value: "agent.plan",
    MessageType.ARTIFACT.value: "agent.artifact",
    MessageType.TEXT.value: "agent.message",
    MessageType.STATUS.value: "agent.message",
    MessageType.COMPLETION.value: "agent.message",
}
```

### 3.4 Streaming Sequence

Within a single agent round:

```
1. thinking_content (stream=true)  ← reasoning text delta (Anthropic only for now)
2. thinking_content (stream=true)  ← more reasoning text
3. thinking (stream=false)         ← tool traces with status/duration
4. text (stream=false)             ← final response text
```

### 3.5 Files to Change

| File | Action |
|------|--------|
| `backend/app/models/message.py` | Add `THINKING_CONTENT` to `MessageType` enum |
| `backend/app/services/agent/agent_service.py` | Add `thinking_content` to EVENT_MAP. Add `timestamp`, `sequence`, `stream` to `_publish_agent_event()`. Add streaming filter (don't persist `stream=true` deltas). |
| `backend/app/services/agent/runtime/loop.py` | Call `llm.stream()` with thinking callback. Emit `thinking_content` events. Emit final complete thinking event for persistence. |
| `frontend/lib/types.ts` | Add `thinking_content` to `AgentMessageType` union. Add `thinkingContent` to `ChatMessage` type. |
| `frontend/hooks/use-events.ts` | **Add `"agent.thinking_content"` to the `agentEvents` array** (line 157 — Codex Finding #9) |
| `frontend/lib/chat-utils.ts` | **Add `thinking_content` normalization** — collect thinking content text into `ChatMessage.thinkingContent` field, similar to how `thinking` events produce `ChatMessage.thinking` (Codex Finding #9) |
| `frontend/hooks/use-chat-stream.ts` | Handle new event type in stream processing |
| `frontend/components/bioinfoflow/thinking-block.tsx` | Full redesign — add container, reasoning text, tool pills |
| `frontend/components/bioinfoflow/chat/message-list.tsx` | Pass `thinkingContent` from ChatMessage to ThinkingBlock |

---

## 4. Thinking Block UI Redesign

### 4.1 Design Direction

Claude-style collapsible container. No sparkle icon. "Thinking..." label with live reasoning text.

### 4.2 Visual Specifications

**Container:**
- Background: `bg-muted/30` (warm subtle, Tailwind)
- Border: `border border-border/50`
- Corners: `rounded-xl`
- Padding: `p-4`
- Only visible when expanded

**Header (collapsed):**
- "Thinking · 12s" — `text-sm text-muted-foreground`
- Chevron right (`›`) when collapsed, down (`▾`) when expanded
- No icon, no emoji

**Header (streaming):**
- Pulsing dot: `bg-foreground/70`, opacity animation `[1, 0.3, 1]` at 1.2s
- "Thinking..." — `text-sm text-muted-foreground`
- Chevron down

**Reasoning text (inside container):**
- `text-sm text-muted-foreground/80 italic leading-relaxed`
- Streamed in real-time during execution
- Line height: `1.6`
- Draft-like feel — not the final answer

**Tool pills (inside container, below reasoning text):**
- `bg-muted px-2.5 py-0.5 rounded-full text-xs text-muted-foreground`
- Horizontal flex wrap
- Status icon prefix: ✓ (done), ● (active), ! (error)
- Human-readable labels (e.g., "Search workflows" not "search_workflows")

**State machine:**
- During streaming: auto-expanded, shows pulsing dot + "Thinking..." + live text
- On completion: auto-collapses to "Thinking · Xs"
- Click to expand/collapse

### 4.3 Component Props

```typescript
interface ThinkingBlockProps {
  // Existing
  summary: string[]
  tools?: ToolTraceItem[]
  defaultExpanded?: boolean
  isStreaming?: boolean
  // New
  thinkingContent?: string        // reasoning text from extended thinking
  thinkingContentStreaming?: boolean  // is reasoning text still arriving
}
```

### 4.4 Data Flow (Frontend)

In `message-list.tsx`, when grouping events into turns:

```typescript
// Within a turn, collect thinking data:
const thinkingContentMessages = messages.filter(m => m.type === "thinking_content")
const thinkingMessages = messages.filter(m => m.type === "thinking")

// Concatenate all thinking_content into one string
const reasoningText = thinkingContentMessages.map(m => m.content).join("")

// Extract tool traces from thinking messages (existing logic)
const allTools = thinkingMessages.flatMap(m => m.metadata?.tools || [])

// Pass to ThinkingBlock
<ThinkingBlock
  summary={allSummary}
  tools={allTools}
  thinkingContent={reasoningText}
  thinkingContentStreaming={isStreaming}
  isStreaming={isStreaming}
/>
```

### 4.5 Files to Change

_(See Section 3.5 for the complete frontend file list — includes `use-events.ts`, `chat-utils.ts`, `use-chat-stream.ts`, `types.ts`, `thinking-block.tsx`, `message-list.tsx`)_

---

## 5. Migration & Compatibility

### 5.1 Breaking Changes

- **LangChain removal**: `langchain-anthropic`, `langchain-openai`, `langchain-google-genai` dependencies removed
- **Legacy tools removed**: `validate_workflow`, `scan_dir`, `search_workflows`, `list_images`, `read_logs`, `visualize_result`
- **v1 graph fallback**: `graph.py` still references LangChain — needs `anthropic_disabled` check or removal

### 5.2 Non-Breaking Changes

- New SSE fields (`timestamp`, `sequence`, `stream`) — frontend ignores unknown fields
- New message type `thinking_content` — frontend handles gracefully (unknown types render as text)
- New config settings have sensible defaults

### 5.3 ~~Alembic Migration~~ No Migration Needed (Codex Finding #7)

`messages.type` is stored as `String(20)`, not a DB enum. Adding `THINKING_CONTENT` to the Python `MessageType` enum is sufficient — no Alembic migration needed.

**However, an Alembic migration IS needed for `user_settings`:** Adding `openrouter_api_key`, `ollama_base_url`, `ollama_model` columns to the `user_settings` table requires a schema migration.

### 5.3.1 Thinking Content Persistence Strategy (Codex Finding #7)

**Do NOT persist every streaming `thinking_content` delta as a separate message row.** The current `_persist_and_publish_agent_event()` creates one DB row per event — persisting 50+ thinking deltas per round would be garbage for storage and replay.

Instead:
- **During streaming:** Emit `thinking_content` deltas via SSE only (no DB persistence)
- **After round completes:** Persist ONE `thinking_content` message with the full concatenated reasoning text
- The `on_event` callback in `agent_service.py` needs a filter: skip persistence for events with `stream=true`, persist the final complete event only

### 5.4 v1 Graph Cleanup

The legacy v1 LangGraph agent (`graph.py`) depends on LangChain. Options:
- **Option A**: Delete `graph.py` and the `agent_runtime_v2` feature flag (v2 is the default and has been stable)
- **Option B**: Keep `graph.py` but make it import-gated (only loads if LangChain is installed)

Recommend **Option A** — the v2 runtime has been stable and v1 is unused.

---

## 6. Implementation Phases

### Phase 1: LLM Providers (highest impact)
1. Create `providers.py` with registry
2. **Delete `graph.py`** and remove v1 routing from `agent_service.py` (must happen BEFORE removing LangChain deps — Codex Finding #3)
3. Refactor `llm_client.py` — add native OpenAI and Gemini calls, add `stream()` method
4. Add OpenRouter and Ollama support (base_url pattern)
5. Add extended thinking to Anthropic path (budget_tokens + thinking block extraction)
6. Update `config.py` with new settings, remove `agent_runtime_v2` flag
7. Delete `llm_providers.py`
8. Remove LangChain dependencies from `pyproject.toml` (LAST — after all imports are cleaned)
9. Add `openrouter_api_key`, `ollama_base_url`, `ollama_model` to `user_settings` model + Alembic migration
10. Update `user_settings` schema, service, and frontend settings UI for new providers

### Phase 2: Tool Refactor
1. Create `GlobTool` in `file_tools.py`
2. Rename and enhance `code_search` → `GrepTool` in `search_tools.py`
3. Create `WebSearchTool` in `web_tools.py`
4. Create `ShellTool` in `shell_tool.py` (extracted from legacy, with expanded commands/limits)
5. Move `search_workflows`, `list_images`, `read_logs`, `validate_workflow` to inline handlers in `dispatch.py` (thin service wrappers, not CLI calls)
6. Delete `workflow_tools.py`, `legacy_tools.py`
7. Refactor `dispatch.py` — remove `_register_legacy_tools()`, register new BaseTool instances + inline handlers
8. Enhance `system_prompt.py` — add bioinformatics CLI guide, git instructions, file types
9. **Update `DeterministicTestClient`** — replace `scan_dir` tool call with `glob` (Codex Finding #8)
10. Update system prompt to remove references to deleted tool names
11. Add risk-level enforcement to `loop.py` tool dispatch

### Phase 3: Event System + Thinking UI
1. Add `THINKING_CONTENT` to `MessageType` enum (no Alembic needed — String column)
2. Update `agent_service.py` — new event envelope fields (`timestamp`, `sequence`, `stream`), streaming persistence filter
3. Update `loop.py` — call `llm.stream()` with thinking callback, emit `thinking_content` events
4. Update `use-events.ts` — add `"agent.thinking_content"` to subscribed events
5. Update `chat-utils.ts` — normalize `thinking_content` events into `ChatMessage.thinkingContent`
6. Update `types.ts` — add `thinking_content` type, `thinkingContent` field on `ChatMessage`
7. Redesign `thinking-block.tsx` — container, reasoning text, tool pills
8. Update `message-list.tsx` — pass `thinkingContent` to ThinkingBlock

### Parallelization

Phase 1 and Phase 2 are independent (different files, no shared changes) — can be worked in parallel by 2 agents. Phase 3 depends on Phase 1 (extended thinking) but not on Phase 2. With 3 agents: Agent 1 = Phase 1, Agent 2 = Phase 2, Agent 3 = Phase 3 (starts after Agent 1 lands the `LLMResponse.thinking` field).

---

## 7. Testing Strategy

### Backend
- **Provider tests**: Mock each SDK's async client. Test that `LLMClient` normalizes responses correctly across all 5 providers.
- **Tool tests**: Test `glob`, `grep`, `web_search` with fixture directories.
- **Event tests**: Verify new fields appear in SSE events. Verify `thinking_content` events flow correctly.
- **Integration**: End-to-end agent loop test with `DeterministicTestClient` — verify thinking events are emitted.

### Frontend
- **ThinkingBlock**: Unit test all states (collapsed, expanded, streaming, with/without reasoning text).
- **Message list**: Integration test that `thinking_content` events are correctly grouped and passed.
- **Coverage**: Maintain 80% threshold.

---

## 8. Codex Review — Findings & Resolutions

Codex (GPT-5.4) reviewed this spec against the actual codebase. 11 findings, all addressed:

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | Streaming is fake — `LLMClient.create()` blocks, can't stream thinking deltas | High | Added `LLMClient.stream()` method spec. Interim fallback: emit thinking as complete event. (§1.3.1) |
| 2 | OpenRouter model inference bug — `"claude"` check matches before `"/"` | Medium | Fixed: check `"/"` first in `_infer_provider_from_model()`. (§1.7) |
| 3 | LangChain removal ordering — v1 imports break if deps removed first | High | Fixed: delete `graph.py` and v1 routing BEFORE removing deps. (§1.6, §6 Phase 1) |
| 4 | Risk levels not enforced in v2 loop | High | Added risk-level enforcement spec for `loop.py`. READ→auto, ACT_LOW→log, ACT_HIGH→approval. (§2.5) |
| 5 | safe_shell has 10s timeout, 4K char limit | Medium | Fixed: new `ShellTool` with 120s timeout, 50K char limit. (§2.5) |
| 6 | Service-backed tools → CLI is a regression | Medium | Revised: keep 4 domain tools as thin inline handlers calling services directly. (§2.2, §2.5.1) |
| 7 | Alembic migration not needed for String column | Low | Fixed: removed false claim. Added persistence strategy for streaming chunks. (§5.3, §5.3.1) |
| 8 | Test clients reference deleted tools | Medium | Fixed: added step to update `DeterministicTestClient` and system prompt. (§6 Phase 2) |
| 9 | Frontend scope incomplete — misses `use-events.ts`, `chat-utils.ts` | High | Fixed: added all missing frontend files to scope. (§3.5) |
| 10 | Provider expansion needs user settings changes | Medium | Fixed: added user_settings model, schema, service, and frontend to Phase 1 scope. (§1.6) |
| 11 | Over-scoped bundle | Advisory | Acknowledged. Phased approach + 3 parallel agents mitigate risk. |

---

## Appendix: Research Sources

- [GPT-5.4 vs Claude Opus 4.6 vs Gemini 3.1 Pro: 2026 Developer Comparison](https://evolink.ai/blog/gpt-5-4-vs-claude-opus-4-6-vs-gemini-3-1-pro-2026)
- [Frontier AI Models Face Off](https://www.tweaktown.com/articles/11373/frontier-ai-models-face-off-gpt-5-4-vs-gemini-3-1-pro-vs-claude-opus-4-6-vs-grok-4-20/index.html)
- [OpenRouter LangChain Integration](https://openrouter.ai/docs/guides/community/langchain)
- [langchain-openrouter on PyPI](https://pypi.org/project/langchain-openrouter/)
- [Building with Extended Thinking - Claude API](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)
- [Reasoning Models - OpenAI API](https://developers.openai.com/api/docs/guides/reasoning)
- [Gemini 3 Developer Guide](https://ai.google.dev/gemini-api/docs/gemini-3)
- [Gemini 3.1 Pro on OpenRouter](https://openrouter.ai/google/gemini-3.1-pro-preview)
