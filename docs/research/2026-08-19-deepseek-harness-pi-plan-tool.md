# DeepSeek Harness and pi.dev plan-tool research

Date: 2026-08-19

This note answers three questions relevant to BioinfoFlow's plan-card failure:

1. Do DeepSeek Harness and pi.dev expose a plan/todo tool?
2. How do they preserve one assistant tool-call round and provider reasoning data?
3. Where is the seam between harness state and UI presentation?

The sources below are pinned to the inspected commits:

- DeepSeek Harness: [`deepseek-ai/deepseek-harness`](https://github.com/deepseek-ai/deepseek-harness/tree/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca) at `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`.
- pi.dev: [`earendil-works/pi`](https://github.com/earendil-works/pi/tree/59a71b235dadb4ad0d67557a8abb0aaa093e68b4) (the repository formerly known as `pi-mono`) at `59a71b235dadb4ad0d67557a8abb0aaa093e68b4`.

## Conclusions

DeepSeek Harness provides a model-facing `todo_write` tool. pi.dev does not include a plan tool among its built-ins, but ships todo and plan-mode examples through its extension API. Despite that difference, both projects obey the same important invariant:

> One model response remains one canonical assistant message containing its reasoning and all tool calls. Tools execute from that message; the harness does not synthesize a second assistant message for a special control tool.

Provider-specific reasoning fields belong in the model adapter. UI plan state belongs in a domain projection or extension-owned state, not in transcript-shape inspection. These boundaries directly avoid the BioinfoFlow failure mode in which extracting `update_plan` produced an assistant tool-call message without DeepSeek's required `reasoning_content`.

This invariant is also stated by DeepSeek's official [Thinking Mode guide](https://api-docs.deepseek.com/guides/thinking_mode): during a tool-call sequence, every sub-request must pass the prior response's `reasoning_content` back, and the example appends the model-returned assistant message containing `content`, `reasoning_content`, and `tool_calls` directly to history.

## DeepSeek Harness

### `todo_write` is an ordinary tool with whole-list semantics

The tool is named `todo_write`, not `update_plan`. Every invocation supplies the complete list and replaces the previous list. Items use `pending`, `in_progress`, or `completed`; the tool may enforce a single active item or permit parallel active items. Its execution appends a `todo/write` event to the owning agent session and returns counts. It does not create an assistant message or manipulate provider history.

Sources:

- [`packages/todo/tool-todo/src/index.ts`, tool contract and status rules](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/todo/tool-todo/src/index.ts#L45-L110)
- [`packages/todo/tool-todo/src/index.ts`, registration and execution](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/todo/tool-todo/src/index.ts#L122-L225)

### The assistant round is preserved as one unit

The agent persists the completed assistant response once, then extracts all tool-call blocks and schedules them together. The scheduler may form sequential or parallel execution groups, but results are committed in the model's source order. There is no special path that removes `todo_write` from the assistant response.

Sources:

- [`packages/core/agent-loop/src/agent.ts`, persist response then schedule all calls](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/agent-loop/src/agent.ts#L373-L399)
- [`packages/core/agent-loop/src/tool-calls.ts`, batch planning and ordered commit](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/agent-loop/src/tool-calls.ts#L59-L101)
- [`packages/core/agent-loop/src/tool-calls.ts`, result ordering](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/core/agent-loop/src/tool-calls.ts#L145-L159)

### The DeepSeek adapter owns `reasoning_content`

The harness-level message is provider-neutral content blocks: text, reasoning, and tool calls. The DeepSeek serializer reconstructs one wire assistant message containing `content`, `reasoning_content`, and the complete `tool_calls` array. It emits `reasoning_content` on tool-call turns according to DeepSeek's passback rule. A focused test locks this behavior down.

Sources:

- [`packages/llm/llm-deepseek/src/serialize.ts`, assistant serialization](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/llm/llm-deepseek/src/serialize.ts#L70-L101)
- [`packages/llm/llm-deepseek/tests/serialize.spec.ts`, reasoning passback test](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/llm/llm-deepseek/tests/serialize.spec.ts#L47-L80)

### Plan UI consumes a projection, not harness internals

The tool package optionally registers a `todos` session projection. It folds `todo/write` as last-write-wins state, retains the finished list through `turn/end`, and clears it on the next `turn/start`. Headless deployments are unaffected when the projection seam is absent.

The web component receives a plain `TodoItem[]`. A small dock adapter reads `useProjection('todos')`; a slot registration chooses where the panel is mounted. The current DeepSeek web UI mounts it above the composer, not in the transcript or right sidebar, but the slot boundary makes placement a UI decision rather than a harness change.

Sources:

- [`packages/todo/tool-todo/src/index.ts`, projection fold](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/todo/tool-todo/src/index.ts#L122-L148)
- [`packages/todo/tool-todo/tests/projection.spec.ts`, last-write-wins and retirement behavior](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/todo/tool-todo/tests/projection.spec.ts#L77-L105)
- [`TodoPanel.tsx`, plain component and projection adapter](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-conversation/src/client/skeleton/TodoPanel.tsx#L1-L24)
- [`TodoPanel.tsx`, `useProjection` and slot registration](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-conversation/src/client/skeleton/TodoPanel.tsx#L130-L153)
- [`assembly-surfaces.client.spec.tsx`, projection update and retirement](https://github.com/deepseek-ai/deepseek-harness/blob/99f6f02fecdb7dff40c3fbc9470f5907c29f74ca/packages/client/ui-tool/tests/assembly-surfaces.client.spec.tsx#L94-L124)

## pi.dev / pi

### Planning is extension-owned, not a built-in harness special case

pi's built-in coding tools are `read`, `bash`, `edit`, `write`, `grep`, `find`, and `ls`; there is no built-in `update_plan` or `todo_write`. The repository instead demonstrates both behaviors as extensions.

The todo extension registers a normal `todo` tool. State is stored in tool-result `details` and reconstructed from branch history, so replay and branching produce the state appropriate to that point in history. Rendering lives beside the extension through `renderCall` and `renderResult` rather than in the core agent loop.

The plan-mode example parses numbered plan text and `[DONE:n]` markers. It uses `ctx.ui.setStatus` and `ctx.ui.setWidget`, persists extension state, updates progress at `turn_end`, and clears `executionMode`, todo items, status, and widget when `agent_end` observes all items complete.

Sources:

- [`packages/coding-agent/src/core/tools/index.ts`, built-in tool set](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/src/core/tools/index.ts#L81-L115)
- [`examples/extensions/todo.ts`, state model and reconstruction](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/examples/extensions/todo.ts#L1-L10)
- [`examples/extensions/todo.ts`, tool registration and execution](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/examples/extensions/todo.ts#L105-L219)
- [`examples/extensions/todo.ts`, extension-side rendering](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/examples/extensions/todo.ts#L221-L281)
- [`examples/extensions/plan-mode/index.ts`, UI state adapter](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/examples/extensions/plan-mode/index.ts#L47-L84)
- [`examples/extensions/plan-mode/index.ts`, terminal completion cleanup](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/coding-agent/examples/extensions/plan-mode/index.ts#L249-L275)

### One assistant message owns every tool call

The pi agent loop streams one assistant message into context, extracts all `toolCall` blocks from that same message, executes the batch, appends ordered tool-result messages, and only then starts the next model turn. Sequential and parallel execution are execution-policy choices; neither rewrites the source assistant message.

Sources:

- [`packages/agent/src/agent-loop.ts`, assistant message and tool batch](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/agent/src/agent-loop.ts#L192-L224)
- [`packages/agent/src/agent-loop.ts`, sequential and parallel execution](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/agent/src/agent-loop.ts#L420-L563)

### Provider compatibility remains in the adapter

pi's canonical `AssistantMessage` carries thinking and tool-call blocks. Its OpenAI-compatible adapter captures reasoning fields from stream deltas, records the field name as a signature, and replays the reasoning on the assistant wire message. Compatibility detection recognizes DeepSeek by provider or URL and enables `requiresReasoningContentOnAssistantMessages`, adding an empty `reasoning_content` when reasoning is enabled but a replayed assistant message has none.

Sources:

- [`packages/ai/src/types.ts`, canonical thinking and tool-call blocks](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/ai/src/types.ts#L347-L379)
- [`openai-completions.ts`, reasoning delta capture](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/ai/src/api/openai-completions.ts#L492-L523)
- [`openai-completions.ts`, assistant reasoning and tool-call replay](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/ai/src/api/openai-completions.ts#L1155-L1255)
- [`openai-completions.ts`, DeepSeek compatibility detection](https://github.com/earendil-works/pi/blob/59a71b235dadb4ad0d67557a8abb0aaa093e68b4/packages/ai/src/api/openai-completions.ts#L1490-L1538)

## First-principles implications for BioinfoFlow

The smallest design that satisfies model correctness, harness upgradeability, and UI correctness is:

1. **Preserve the model turn.** Store one immutable canonical assistant message containing reasoning, text, and every tool call. Never extract `update_plan` into a synthetic assistant round.
2. **Execute planning like any other tool.** The plan tool may have sequential execution policy if necessary, but policy operates on the call batch; it must not change conversation history.
3. **Let the provider adapter own wire quirks.** DeepSeek's `reasoning_content` passback is a codec concern. The harness should only expose canonical reasoning blocks and tool calls.
4. **Emit plan domain state.** A successful plan-tool execution should publish a typed whole-plan snapshot. Whole-list replacement is simpler to replay and avoids partial-update ordering ambiguity.
5. **Project state for clients.** An adapter/projection should fold plan snapshots and terminal lifecycle events into a small frontend contract such as `PlanSnapshot | null`. The React component should not inspect transcript tool messages or import harness internals.
6. **Make placement a frontend composition choice.** Mount a compact progress trigger above the composer and open the full plan upward, outside the transcript. Changing this slot must not require changes to harness execution or provider codecs.
7. **Define terminal settlement.** On success, failure, cancellation, or interruption, no plan item may retain a live animation. A completed Run can settle every item to completed; other terminal outcomes may preserve factual item statuses while rendering them statically. This must be driven by Run lifecycle, not animation timeouts or inference from a stale transcript row.

This is not an argument for copying either project wholesale. The reusable invariant is the narrow boundary:

```text
provider adapter <-> canonical assistant turn <-> ordinary tool execution
                                              |
                                              v
                                      plan domain snapshot
                                              |
                                              v
                                      frontend adapter/slot
```

That boundary lets the harness evolve without coupling the plan card to internal event shapes, while preserving the exact model history required by DeepSeek thinking mode.
