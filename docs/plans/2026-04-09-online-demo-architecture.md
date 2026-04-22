# Plan: README Rewrite + Online Demo Architecture Design

## Context

Two tasks:
1. **README rewrite** — Add hero GIF placeholder, pitch-first structure ("Like Cursor, but for bioinformatics pipelines"), reorganize existing commands without deleting them.
2. **Online demo design** — Design a cinematic auto-play demo system that replays pre-recorded SSE events in the browser. Same Next.js app deployed to Vercel with `DEPLOY_MODE=demo` env var. No backend needed. OAuth re-enabled for the demo landing page only.

## Part 1: README Rewrite

### Changes to `README.md`

**New structure:**
```
1. Title + tagline ("Like Cursor, but for running bioinformatics pipelines. Locally.")
2. Hero GIF placeholder (docs/assets/demo.gif)
3. "What This Is" — 2 sentences
4. "Try It" — 3-step Docker quick start (existing, moved up)
5. "What Just Happened" — 3 bullets explaining what's running
6. --- separator ---
7. "Auth Modes" table (existing)
8. "Remote Deployment" section (existing)
9. "Local Development" section (existing, moved down)
10. "CLI" section (existing)
11. "Docker" section (existing)
12. "Tests" section (existing)
13. "Deployment" section (existing)
```

Key: Nothing deleted. Pitch moves to top, technical reference moves below the fold.

**File**: `README.md`
**Also create**: `docs/assets/` directory (empty placeholder for demo.gif)

## Part 2: Online Demo Architecture Design

### Overview

Record real SSE events from a pipeline run → save as NDJSON → replay in browser with compressed timing. The same Next.js app serves both the real app (Docker) and the demo site (Vercel), gated by `DEPLOY_MODE` env var.

### Architecture

```
┌─────────────────────────────────────────────────┐
│  Vercel (DEPLOY_MODE=demo)                       │
│                                                   │
│  bioinfoflow.io                                   │
│  ├── /              Landing page                  │
│  ├── /auth          OAuth login (GitHub/Google)    │
│  └── /demo          Auto-play cinematic replay    │
│                                                   │
│  No FastAPI backend. No real data.                │
│  NDJSON recording → client-side replay engine     │
│  → same React components render the experience    │
└─────────────────────────────────────────────────┘
```

### How replay works

The key insight: `applySSEEvent()` in `frontend/lib/chat-utils.ts` is a **pure function**. It takes `(messages[], event)` → returns `newMessages[]`. The DAG component takes `DagData` as a prop. This means:

1. **Record** real SSE events during an actual pipeline run → NDJSON file
2. **Replay** by reading the NDJSON, scheduling events with `setTimeout`, calling `applySSEEvent()` sequentially
3. **Components** (ChatStream, DagPanel, RunStatus) receive state updates identically to real mode — they can't tell the difference

### Timing compression

Original events may span 30+ minutes. Replay compresses to ~90 seconds:
- Proportional spacing between events, but capped at 2-second max gaps
- Text deltas play at realistic typing speed (~30ms per delta)
- DAG status transitions get brief pauses (~500ms) for visual impact

### File structure (new files)

```
frontend/
  app/
    (demo)/                          ← NEW route group
      layout.tsx                     ← DemoReplayProvider, minimal chrome
      page.tsx                       ← Auto-play demo page
    (landing)/                       ← NEW route group
      page.tsx                       ← Public landing page
  lib/
    demo/                            ← NEW module
      replay-engine.ts               ← Core: read NDJSON, schedule events
      demo-context.tsx               ← React context for demo state
      use-demo-chat.ts               ← Drop-in for useAgentChat()
      use-demo-events.ts             ← Drop-in for useEvents()
      recordings/
        ecoli-qc-run.ndjson          ← Pre-recorded pipeline run
  middleware.ts                      ← MODIFY: add DEPLOY_MODE gate
```

### Recording format (NDJSON)

Each line is a JSON object matching the existing `EventEnvelope` type:
```json
{"t":0,"event":"agent.message","data":{"id":"m1","content":"I'll run a QC check on your E. coli samples."}}
{"t":150,"event":"agent.text_delta","data":{"id":"m2","content":"Setting"}}
{"t":180,"event":"agent.text_delta","data":{"id":"m2","content":" up"}}
{"t":2500,"event":"run.status","data":{"run_id":"r1","status":"running","current_task":"READS_STATS"}}
{"t":5000,"event":"run.dag","data":{"run_id":"r1","dag":{"nodes":[...],"edges":[...]}}}
```

`t` = milliseconds from start (replay offset). This is simpler than full ISO timestamps and makes timing compression trivial.

### DEPLOY_MODE middleware gate

In `frontend/middleware.ts`:
```typescript
const deployMode = process.env.DEPLOY_MODE || 'app'

if (deployMode === 'demo') {
  // Allow: /, /demo/*, /auth/*, /api/auth/*
  // Everything else → redirect to /
}
```

### OAuth re-enablement

Restore from commit `1295be33^` (April 7, 2026):
- Add back `authSocialProviders` in `auth-config.ts` (conditional on env vars)
- Add `socialProviders` to Better Auth init in `auth.ts`
- Restore OAuth buttons in login page
- On Vercel: set `GITHUB_CLIENT_ID`, `GOOGLE_CLIENT_ID` env vars
- On Docker (self-hosted): don't set them → OAuth buttons hidden automatically

### Vercel deployment config

```json
// vercel.json
{
  "framework": "nextjs",
  "buildCommand": "bun run build",
  "env": {
    "DEPLOY_MODE": "demo",
    "NEXT_PUBLIC_AUTH_MODE": "personal",
    "BETTER_AUTH_URL": "https://bioinfoflow.io"
  }
}
```

### Recording workflow (developer-only, one-time)

1. Run the real app locally with a demo pipeline (e.g., ecoli-qc)
2. Open browser DevTools → Network → filter EventSource
3. Or: add a `--record` flag to the SSE endpoint that writes events to a file
4. Better: create a `scripts/record-demo.ts` script that:
   - Connects to `/api/v1/events/stream`
   - Sends a pre-defined agent message
   - Captures all events until `agent.done` + `run.status=completed`
   - Writes NDJSON with `t` offsets

### Existing code to reuse

| Existing | Reused for |
|----------|-----------|
| `lib/chat-utils.ts:applySSEEvent()` | Core replay logic — same function |
| `lib/chat-types.ts:ChatMessage` | Same data model |
| `hooks/use-events.ts:EventEnvelope` | Same event format |
| `components/bioinfoflow/chat-stream.tsx` | Same chat UI |
| `components/bioinfoflow/dag/dag-panel.tsx` | Same DAG visualization |
| `middleware.ts` | Extend with DEPLOY_MODE check |
| `lib/auth-config.ts` | Extend with OAuth provider detection |

## Implementation Order

### Phase 1 (this session): README rewrite
1. Restructure README with pitch-first layout
2. Add hero GIF placeholder
3. Create `docs/assets/` directory
4. Commit

### Phase 2 (future session): Demo replay system
1. Create `lib/demo/` module (replay engine, context, hooks)
2. Create `(demo)/` and `(landing)/` route groups
3. Add DEPLOY_MODE gate to middleware
4. Record a real ecoli-qc demo run as NDJSON
5. Test locally with `DEPLOY_MODE=demo bun run dev`

### Phase 3 (future session): OAuth + Vercel deploy
1. Re-enable OAuth from git history
2. Set up Vercel project + domain
3. Configure env vars on Vercel
4. Deploy + test

## Verification (Phase 1 only)

1. `README.md` has hero GIF placeholder, pitch section, all existing commands preserved
2. `docs/assets/` directory exists
3. Commit is clean
