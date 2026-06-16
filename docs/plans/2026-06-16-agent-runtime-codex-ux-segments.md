# Agent Runtime Codex UX implementation design

## Runtime modes

The existing agent runtime continues to serve the browser workbench. This change keeps backend events unchanged and adds a frontend-only canonical transcript projection so streaming, replayed, completed, failed, and approval-waiting turns share one display contract.

## Turn loop

Each turn is rendered from `AgentRuntimeTimelineEntry.segments`, ordered by event sequence. `assistant.text` remains a derived compatibility summary only. Terminal states add explicit error/cancelled segments instead of hiding behind text or tool output.

## Tool model

Tool/action/artifact events are still aggregated by the existing activity builder, but activities carry sequence bounds. Transcript rendering exposes them as compact expandable rows in the same timeline as text and decisions.

## Context and memory model

Todo artifacts remain artifact payloads. A display-only projection maps the latest todo artifact plus owning turn status into spinner-safe task state for the dock and progress views.

## Delegation and orchestration model

Approvals, plan approvals, and ask-user prompts have a single full-control surface: the transcript decision segment. Composer and side/drawer surfaces may only show lightweight non-blocking indicators or jumps.

## Extension model

Files browsing keeps the existing one-level lazy backend API and replaces the frontend navigator with an expandable cached tree, preserving file preview and add-to-context hooks.

## Safety and observability model

Unit tests cover segment ordering, snapshot/event text coexistence, multi-message text blocks, terminal errors, single approval controls, terminal todo state, and lazy tree expansion. Each phase is validated and committed separately.
