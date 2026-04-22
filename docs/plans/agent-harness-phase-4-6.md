# Agent Harness Enhancement — Phase 4-6 Plan

## Context

Phases 1-3 established the safety floor (approval UI, error boundaries, file upload cleanup), basic UX polish (status overlay, tool previews, message edit), and engineering hardening (SSE buffering, shiki singleton, cancel confirmation). Code review identified and fixed 6 additional issues (stale closures, stuck state, clipboard errors, ARIA, double-submit guard, cache eviction).

This plan covers what's still missing to bring the bioinfoflow agent from "working prototype" to "production-grade harness" — drawing from Claude Code's architecture patterns.

---

## What Bioinfoflow Already Has (Strong Foundation)

| Area | Status |
|------|--------|
| **3-layer context compaction** (micro/auto/manual) | ✅ `runtime/compact.py` |
| **Skill system** (SKILL.md discovery + `load_skill` tool) | ✅ `runtime/skills.py` |
| **Subagent delegation** (`task` tool → child agent loop) | ✅ `runtime/subagent.py` |
| **Task DAG** (`task_create/update/get/list` tools) | ✅ `runtime/tasks.py` |
| **Todo manager** (session-scoped checklist) | ✅ `runtime/todo.py` |
| **Background shell** (`background_run` tool) | ✅ `runtime/background.py` |
| **Multi-provider LLM** (Anthropic/OpenAI/Gemini via LiteLLM) | ✅ `runtime/llm_client.py` |
| **Extended thinking** with streaming timer | ✅ `thinking-part.tsx` |
| **Approval workflow** (ACT_HIGH → user approve/deny) | ✅ (Phase 1) |
| **Trace/observability** (agent.prompt, agent.response, tool traces) | ✅ `trace.py` |
| **Conversation persistence** (sidebar list, rename, pin, delete) | ✅ `conversation-item.tsx` |

---

## Gap Analysis — What's Missing

### Phase 4: Harness Intelligence (Backend)

#### 4.1 Token Usage Tracking & Surfacing
**What exists:** `llm_client.py` and `llm_streaming.py` track `usage` from LiteLLM responses.
**What's missing:** Usage is logged but not exposed to the frontend. No per-conversation cost reporting.

**Implementation:**
- Backend: Emit `agent.usage` SSE event after each LLM call with `{ prompt_tokens, completion_tokens, model, estimated_cost_usd }`
- Backend: Accumulate per-conversation token totals in `SessionState`
- Frontend: Add a small token counter in `chat-stream.tsx` footer (e.g., "3.2k tokens used")
- Frontend: Show per-message token breakdown on hover (developer mode)

**Files:**
- `backend/app/services/agent/runtime/loop.py` — emit usage event
- `backend/app/services/agent/runtime/session_state.py` — accumulate totals
- `frontend/hooks/use-agent-chat.ts` — handle `agent.usage` event
- `frontend/components/bioinfoflow/chat-stream.tsx` — render counter

#### 4.2 Context Window Pressure Indicator
**What exists:** Backend has `agent_compact_threshold` (50k tokens) and auto-compaction.
**What's missing:** Users have zero visibility into context pressure. They don't know when compaction happens or how close they are to the limit.

**Implementation:**
- Backend: Include `context_tokens` and `max_tokens` in each `agent.done` event metadata
- Frontend: Subtle progress bar under the status overlay showing context fill level
- Color coding: green (<50%), amber (50-80%), red (>80%)
- When compaction fires, show a brief toast: "Context compacted: 48k → 12k tokens"

#### 4.3 Streaming Cancellation Feedback
**What exists:** `stop()` fires cancel and polls status. Backend has `agent.cancelled` event.
**What's missing:** No visual feedback during the cancel → agent stops pipeline.

**Implementation:**
- Frontend: When `stop()` is called, show "Cancelling..." status in the activity bar
- Transition to "Cancelled" briefly before clearing
- If cancel fails (status poll shows still running), show persistent error

#### 4.4 Agent Memory Across Conversations
**What exists:** Each conversation is isolated. No cross-conversation memory.
**What's missing:** The agent forgets everything between conversations. No project-level memory or learnings.

**Implementation:**
- Backend: Add `memory_write` and `memory_read` tools that persist key-value pairs per project
- Storage: New `agent_memories` SQLite table (`project_id, key, value, updated_at`)
- Inject top-N memories into system prompt as "Project Context" section
- Frontend: Show a "Memory" tab in LiveDeck to view/edit what the agent remembers

**Files:**
- `backend/app/models/agent_memory.py` — new ORM model
- `backend/app/repositories/agent_memory_repo.py` — new repo
- `backend/app/services/agent/tools/memory_tools.py` — new tools
- `backend/app/services/agent/runtime/system_prompt.py` — inject memories
- `frontend/components/bioinfoflow/live-deck.tsx` — new "Memory" tab

### Phase 5: User Experience Depth (Frontend)

#### 5.1 Keyboard Shortcuts
**What exists:** `react-hotkeys-hook` is installed as a dependency. Only `Cmd+Shift+B` (sidebar toggle) is implemented.
**What's missing:** All other common shortcuts.

**Implementation:**
- `Cmd+K` — Focus chat input / command palette
- `Cmd+Shift+N` — New conversation
- `Cmd+.` — Stop generation
- `Escape` — Cancel edit mode
- `Cmd+Enter` — Send message (already works via keyDown handler, but not discoverable)
- Add a `?` shortcut overlay (like GitHub's)

**Files:**
- `frontend/app/(app)/agent/page.tsx` — register shortcuts
- `frontend/components/bioinfoflow/chat/shortcuts-overlay.tsx` — new component

#### 5.2 Conversation Export
**What exists:** `lib/conversations.ts` has localStorage helpers. No export.
**What's missing:** Users can't save/share conversations.

**Implementation:**
- Add "Export" dropdown item in conversation context menu (sidebar)
- Formats: Markdown (human-readable), JSON (machine-parseable)
- Markdown format: headings for roles, code blocks preserved, tool calls summarized
- Frontend-only (no backend needed — reconstruct from messages state)

**Files:**
- `frontend/lib/conversation-export.ts` — new: `exportAsMarkdown(messages)`, `exportAsJSON(messages)`
- `frontend/components/bioinfoflow/sidebar/conversation-item.tsx` — add "Export" menu item

#### 5.3 Drag-and-Drop File Upload
**What exists:** File upload button was removed (P0.3) because it was stubbed.
**What's missing:** Real file upload to agent workspace.

**Implementation:**
- Backend: `POST /files/upload` already exists (check `backend/app/api/v1/files.py`)
- Frontend: Add drop zone to `ChatInput` — drag a file onto the input area
- Upload via multipart form → backend saves to project workspace
- Append `[Uploaded: {filename} → {workspace_path}]` to user message
- Agent can then reference the file via `file_read` tool

**Files:**
- `frontend/components/bioinfoflow/chat/chat-input.tsx` — add drag-drop zone
- `frontend/hooks/use-file-upload.ts` — new hook for upload logic

#### 5.4 Inline Code Execution Preview
**What exists:** `execute_code` tool runs Python. Result shown as raw text in tool preview.
**What's missing:** Rich display of code execution (stdout, stderr, return value, charts).

**Implementation:**
- Parse `execute_code` result JSON: `{ stdout, stderr, return_value, artifacts }`
- Show stdout in a terminal-like container
- Show stderr in red
- If artifacts include images (base64), render inline
- Collapsible like other tool results

**Files:**
- `frontend/components/bioinfoflow/chat/parts/tool-call-part.tsx` — enhance `ToolResultPreview` for `execute_code`

### Phase 6: Production Hardening

#### 6.1 Rate Limiting on Agent Endpoints
**What exists:** No rate limiting in backend.
**What's missing:** A runaway client can exhaust LLM API credits.

**Implementation:**
- Add per-user rate limit middleware: 10 messages/minute, 100 messages/hour
- Use in-memory token bucket (no Redis needed for single-instance)
- Return 429 with `Retry-After` header
- Frontend: Show "Rate limited — try again in X seconds" toast

**Files:**
- `backend/app/middleware/rate_limit.py` — new
- `backend/app/api/v1/agent.py` — apply to `/agent/message`

#### 6.2 Graceful LLM Provider Fallback
**What exists:** `llm_client.py` supports multiple providers. Config selects one.
**What's missing:** If the primary provider is down, there's no automatic failover.

**Implementation:**
- Backend: Add `agent_fallback_models` config (ordered list)
- On 429/500/503 from primary, retry with next in list
- Log provider switches as `agent.provider_fallback` events
- Frontend: Show subtle toast "Switched to backup model" so user knows quality may differ

#### 6.3 i18n Compliance
**What exists:** Most strings use `useTranslations`.
**What's missing:** All new Phase 1-3 components have hardcoded English strings (review finding #10).

**Implementation:**
- Add keys to `messages/en.json` and `messages/zh-CN.json`:
  - `agent.approval.*` — "Approval required", "Approved", "Rejected", etc.
  - `agent.tools.*` — "Running tools", "Used N tools", "failed"
  - `agent.actions.*` — "Edit", "Copy", "Regenerate", "Cancel", "Send"
  - `agent.status.*` — "Thinking...", "Responding...", "Running {tool}..."
  - `agent.disclaimer` — "Bioinfoflow Agents can make mistakes..."

#### 6.4 Error Boundary Retry Limit
**What exists:** `ChatErrorBoundary` retries infinitely on click.
**What's missing:** If a message is permanently broken, retry loops forever.

**Implementation:**
- Add `retryCount` state, cap at 3
- After 3 retries, show "This message cannot be rendered" with option to view raw JSON

---

## Implementation Priority

| Phase | Effort | Impact | Recommendation |
|-------|--------|--------|----------------|
| **4.1** Token counter | S | High | Do first — most visible gap |
| **4.2** Context pressure | S | High | Pair with 4.1 |
| **5.1** Keyboard shortcuts | S | Medium | Quick win, big UX lift |
| **6.3** i18n compliance | S | Medium | Compliance debt — clean up |
| **5.2** Conversation export | M | Medium | Common user request |
| **4.3** Cancel feedback | S | Low | Nice polish |
| **4.4** Agent memory | L | Very High | Biggest capability jump |
| **5.3** Drag-drop upload | M | Medium | Restores removed affordance properly |
| **5.4** Code execution preview | M | Medium | Bioinformatics users run lots of code |
| **6.1** Rate limiting | M | High (safety) | Prevent credit runaway |
| **6.2** Provider fallback | M | Medium | Resilience |
| **6.4** Retry limit | S | Low | Edge case fix |

**Recommended order:** 4.1 + 4.2 → 6.3 → 5.1 → 4.4 → 5.2 → 5.3 → rest

---

## Verification

After each sub-phase:
1. `bun run test` — 244+ tests pass
2. `bun run lint` — 0 new issues in modified files
3. Manual smoke: send message → see token count → trigger compaction → verify count resets
4. i18n: switch to zh-CN locale → verify all new strings render Chinese
