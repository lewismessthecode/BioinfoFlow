# Minimal Execution Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or an equivalent isolated-agent workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Agent composer's local/remote single-target selector with a minimalist Auto/Manual execution-location selector.

**Architecture:** Introduce a small `execution_scope` contract while keeping the existing `execution_target` single-target contract compatible. Auto means all configured targets are available and sends no manual target restrictions. Manual means the user selects one or more target ids, including the local target, and the request sends the selected scope. The composer chip displays the selected mode plus a live current-target pill; the pill can animate when the current target label changes.

**Tech Stack:** Next.js 16, React 19, TypeScript, next-intl, Vitest, Testing Library, FastAPI/Pydantic compatibility for AgentCore metadata.

---

## User Model

- Auto: all configured execution locations are available to the agent.
- Manual: the user chooses one or more locations from a list that includes Local and every configured SSH host.
- Local is not a top-level mode. It is one selectable target under Manual.
- The composer chip stays compact: mode label plus a small live current-target pill.
- The dropdown contains only two top-level tabs: Auto and Manual.
- UI copy should be sparse and use the minimalist warm monochrome direction.

## Files

- Modify: `frontend/lib/agent-runtime/types.ts`
  - Add `AgentExecutionScope` and target item types.
- Modify: `frontend/lib/agent-runtime/execution-target.ts`
  - Serialize and resolve execution scope while preserving legacy `execution_target`.
- Modify: `frontend/lib/agent-runtime/client.ts`
  - Send `execution_scope` in session, metadata patch, and turn payloads.
- Modify: `frontend/hooks/use-agent-runtime.ts`
  - Accept `executionScope` on send options and create sessions/turns with it.
- Modify: `frontend/components/bioinfoflow/agent-runtime/connected-node-selector.tsx`
  - Rebuild as Auto/Manual selector with current-target pill.
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
  - Pass execution-scope props to the selector.
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
  - Replace `remoteConnectionOverride` state with execution-scope state and submit it.
- Modify: `frontend/messages/en.json`
  - Add sparse English labels.
- Modify: `frontend/messages/zh-CN.json`
  - Add matching Chinese labels.
- Modify: `backend/app/schemas/agent_core.py`
  - Accept optional `execution_scope` on session and turn requests/reads if needed.
- Modify: `backend/app/services/agent_core/execution_target.py`
  - Normalize legacy target from execution scope for existing permission paths.
- Modify: `backend/app/services/agent_core/service.py`
  - Preserve execution scope in session/turn metadata and continue deriving current single target for compatibility.
- Test: `frontend/tests/unit/components/connected-node-selector.test.tsx`
- Test: `frontend/tests/unit/lib/agent-runtime/client.test.ts`
- Test: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`
- Test: `backend/tests/test_agent_core/test_execution_target.py` or nearest existing AgentCore API/schema tests.

## Phase 1: Contract And Serialization

- [ ] **Step 1: Add failing frontend client tests**

Add tests proving:

```ts
await createAgentRuntimeTurn({
  sessionId: "session-1",
  inputText: "hello",
  executionScope: { mode: "auto" },
})
```

sends:

```json
{ "execution_scope": { "mode": "auto" } }
```

and:

```ts
executionScope: {
  mode: "manual",
  selected_targets: [
    { kind: "local" },
    { kind: "remote_ssh", connection_id: "connection-1" }
  ]
}
```

sends the same manual target list.

Run:

```bash
rtk bun run test tests/unit/lib/agent-runtime/client.test.ts
```

Expected before implementation: FAIL because `executionScope` is not accepted or serialized.

- [ ] **Step 2: Implement frontend serialization**

Add `AgentExecutionScope` and `agentExecutionScopeForRequest()` so request bodies include `execution_scope` when provided. Keep `execution_target` unchanged for legacy single-target callers.

- [ ] **Step 3: Add backend compatibility tests**

Add tests proving:

- `{"mode": "auto"}` normalizes to local compatibility target.
- manual scope with exactly one remote target derives `{"type": "remote_ssh", "connection_id": "<id>"}`.
- manual scope with local plus remote keeps the legacy target local unless an explicit current target is supplied, while selected remote ids remain discoverable for remote tools.

Run the narrow backend test file and expect RED before implementation.

- [ ] **Step 4: Implement backend compatibility**

Accept `execution_scope` on API schemas and metadata. Preserve the full scope in metadata; derive a single compatibility `execution_target` for existing permission/toolset code.

- [ ] **Step 5: Validate and commit phase 1**

Run:

```bash
rtk bun run test tests/unit/lib/agent-runtime/client.test.ts
rtk uv run pytest tests/test_agent_core/test_execution_target.py
```

Commit:

```bash
rtk git add frontend/lib/agent-runtime backend/app/schemas/agent_core.py backend/app/services/agent_core backend/tests/test_agent_core/test_execution_target.py frontend/tests/unit/lib/agent-runtime/client.test.ts
rtk git commit -m "feat: add agent execution scope contract"
```

## Phase 2: Minimal Selector UI

- [ ] **Step 1: Add failing selector tests**

Update `connected-node-selector.test.tsx` to prove:

- the trigger defaults to `Auto`
- Auto tab shows all configured machines as available without individual checkboxes
- Manual tab exposes Local plus remote hosts with multi-select checkboxes
- selecting Local and a remote emits a manual scope with both targets
- the trigger shows a live current-target pill label

Run:

```bash
rtk bun run test tests/unit/components/connected-node-selector.test.tsx
```

Expected before implementation: FAIL because the component is still local/remote single-select.

- [ ] **Step 2: Implement Auto/Manual selector**

Replace the menu with two tabs. Use warm monochrome styling, tight copy, small status badges, and no explanatory paragraphs. Keep the "Manage SSH hosts" footer. Use existing icon exports only where already established by this repo.

- [ ] **Step 3: Wire composer and workbench**

Pass `executionScope`, `currentTargetLabel`, and `onExecutionScopeChange` from workbench to composer to selector. Convert existing session/project remote default behavior into Manual mode only when there is a remote project default; otherwise default to Auto.

- [ ] **Step 4: Validate and commit phase 2**

Run:

```bash
rtk bun run test tests/unit/components/connected-node-selector.test.tsx tests/unit/components/agent-workbench.test.tsx tests/unit/hooks/use-agent-runtime.test.tsx
rtk bun run lint:i18n
```

Commit:

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime frontend/hooks/use-agent-runtime.ts frontend/messages frontend/tests/unit/components frontend/tests/unit/hooks/use-agent-runtime.test.tsx
rtk git commit -m "feat: simplify agent execution selector"
```

## Phase 3: Visual Verification And Polish

- [ ] **Step 1: Run frontend checks**

Run:

```bash
rtk bun run lint
rtk bun run test
```

- [ ] **Step 2: Visual review**

Set `AUTH_MODE=dev` in the worktree `.env` if local auth blocks the app. Start backend/frontend if needed, open `/agent`, and inspect the composer at desktop and mobile widths. Verify:

- the selector fits in the composer toolbar
- the current-target pill can change without layout shift
- menu copy remains sparse in English and Chinese
- the design follows the minimalist warm monochrome direction

- [ ] **Step 3: Parallel review agents**

Dispatch at least two review agents:

- Frontend/UI review: selector behavior, accessibility, layout.
- Backend/contract review: scope normalization, compatibility, security boundary.

Fix Critical and Important findings, then rerun relevant tests.

- [ ] **Step 4: Final commit and PR**

If review fixes were needed, commit them. Then run final verification, push the branch, and open a draft PR.
