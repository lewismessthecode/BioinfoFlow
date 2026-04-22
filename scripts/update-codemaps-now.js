#!/usr/bin/env node

/**
 * Force update codemaps (bypasses approval)
 */

const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.join(__dirname, '..');
const CODEMAPS_DIR = path.join(PROJECT_ROOT, 'codemaps');

function scanFiles(dir, patterns, exclude = []) {
  const results = [];

  function scan(currentDir) {
    try {
      const entries = fs.readdirSync(currentDir, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = path.join(currentDir, entry.name);
        const relativePath = path.relative(PROJECT_ROOT, fullPath);
        if (exclude.some(ex => relativePath.includes(ex))) continue;
        if (entry.isDirectory()) {
          scan(fullPath);
        } else if (entry.isFile() && patterns.some(p => entry.name.match(p))) {
          results.push(relativePath);
        }
      }
    } catch (err) {}
  }

  scan(dir);
  return results;
}

function analyzeBackend() {
  const backendDir = path.join(PROJECT_ROOT, 'backend');
  const pyFiles = scanFiles(backendDir, [/\.py$/], ['node_modules', '__pycache__', '.venv', '.pytest_cache', 'alembic/versions']);

  return {
    totalFiles: pyFiles.length,
    apiRoutes: pyFiles.filter(f => f.includes('app/api/v1/')),
    services: pyFiles.filter(f => f.includes('app/services/')),
    models: pyFiles.filter(f => f.includes('app/models/')),
    repos: pyFiles.filter(f => f.includes('app/repositories/')),
    schemas: pyFiles.filter(f => f.includes('app/schemas/')),
    tools: pyFiles.filter(f => f.includes('app/services/agent/tools/')),
    tests: pyFiles.filter(f => f.includes('tests/')),
    dependencies: ['FastAPI', 'SQLAlchemy', 'Alembic', 'LangGraph', 'LangChain', 'Docker', 'psutil', 'structlog']
  };
}

function analyzeFrontend() {
  const frontendDir = path.join(PROJECT_ROOT, 'frontend');
  const tsFiles = scanFiles(frontendDir, [/\.(ts|tsx)$/], ['node_modules', '.next', 'dist']);

  return {
    totalFiles: tsFiles.length,
    pages: tsFiles.filter(f => f.includes('app/') && f.includes('page.tsx')),
    layouts: tsFiles.filter(f => f.includes('app/') && f.includes('layout.tsx')),
    components: tsFiles.filter(f => f.includes('components/')),
    hooks: tsFiles.filter(f => f.includes('hooks/')),
    lib: tsFiles.filter(f => f.includes('lib/')),
    tests: tsFiles.filter(f => f.includes('tests/')),
    dependencies: ['next', 'react', 'react-dom', '@radix-ui', 'better-auth', 'reactflow', 'framer-motion']
  };
}

const timestamp = new Date().toISOString().split('T')[0];
const backendData = analyzeBackend();
const frontendData = analyzeFrontend();

// Generate codemaps
const codemaps = {
  'architecture.md': `# Architecture Codemap
**Last Updated:** ${timestamp}
**Entry Points:** \`backend/app/main.py\`, \`backend/app/api/v1/router.py\`, \`backend/app/runtime/events.py\`, \`frontend/app/layout.tsx\`, \`frontend/app/(app)/layout.tsx\`

## Architecture
\`\`\`
Browser (Next.js UI)
   │  REST + SSE
   ▼
FastAPI /api/v1  ───────────────►  SQLite (aiosqlite)
   │                               ▲
   │                               │
   ├─ Services (projects, runs, workflows, files, images, demos)
   │
   ├─ Agent Runtime (LangGraph)
   │    ├─ Tool registry (${backendData.tools.length} tools)
   │    ├─ Planner + Executor
   │    └─ Trace recorder + SSE events
   │
   └─ Workflow execution
        ├─ Nextflow adapter
        └─ MiniWDL adapter
\`\`\`

## Key Modules
| Module | Purpose | Exports | Dependencies |
| --- | --- | --- | --- |
| \`backend/app/main.py\` | FastAPI app creation + router wiring | \`app\` | FastAPI, API router, config |
| \`backend/app/api/v1/router.py\` | API route aggregation | \`api_router\` | API route modules |
| \`backend/app/runtime/events.py\` | SSE event bus | \`publish_event\`, \`subscribe_events\` | asyncio queues |
| \`backend/app/services/agent/graph.py\` | LangGraph agent loop | \`build_agent_graph\` | LangGraph, LLM clients |
| \`backend/app/services/agent/planner.py\` | Multi-step task planning | \`TaskPlanner\`, \`ExecutionPlan\` | LangChain, LLM |
| \`backend/app/services/agent/executor.py\` | Plan execution engine | \`PlanExecutor\` | Planner, tools |
| \`frontend/lib/api.ts\` | API helper with envelope parsing | \`apiRequest\` | Fetch, types |
| \`frontend/hooks/use-events.ts\` | SSE subscription hook | \`useEvents\` | EventSource, types |
| \`frontend/components/bioinfoflow/chat-stream.tsx\` | Chat UI + agent actions | \`ChatStream\` | API + SSE |

## Data Flow
- UI sends REST requests via \`apiRequest\` to \`/api/v1/*\` and renders responses.
- Long-running actions (agent, runs, image pulls) emit SSE events via \`EventBus\` to \`useEvents\`.
- Services orchestrate repositories, workflow adapters, and the agent runtime.
- Agent uses TaskPlanner for multi-step decomposition and PlanExecutor for execution.

## Statistics
- Backend: ${backendData.totalFiles} Python files, ${backendData.apiRoutes.length} API routes, ${backendData.services.length} services, ${backendData.tools.length} tools
- Frontend: ${frontendData.totalFiles} TS/TSX files, ${frontendData.pages.length} pages, ${frontendData.components.length} components
- Tests: ${backendData.tests.length} backend tests, ${frontendData.tests.length} frontend tests

## External Dependencies
- Backend: FastAPI, SQLAlchemy (async), Alembic, LangGraph, LangChain (Anthropic/OpenAI/Gemini), Docker SDK.
- Frontend: Next.js 16, React 19, Radix UI, Better Auth, React Flow, Tailwind CSS, Framer Motion.

## Related Areas
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
- [Data Codemap](data.md)
`,

  'backend.md': `# Backend Codemap
**Last Updated:** ${timestamp}
**Entry Points:** \`backend/app/main.py\`, \`backend/app/api/v1/router.py\`, \`backend/alembic/env.py\`, \`backend/scripts/init_db.py\`

## Architecture
\`\`\`
HTTP /api/v1
   │
   ▼
API Routers → Services → Repositories → SQLite (aiosqlite)
   │              │
   │              ├─ Workflow adapters (Nextflow/MiniWDL)
   │              ├─ Agent runtime (LangGraph + ${backendData.tools.length} tools)
   │              └─ Planning system (Planner + Executor)
   │
   └─ SSE EventBus (runtime/events.py)
\`\`\`

## API Routes (${backendData.apiRoutes.length} routes)
| Prefix | Module | Notes |
| --- | --- | --- |
| \`/projects\` | \`backend/app/api/v1/projects.py\` | CRUD + search |
| \`/workflows\` | \`backend/app/api/v1/workflows.py\` | Registry + metadata |
| \`/runs\` | \`backend/app/api/v1/runs.py\` | Run lifecycle + logs |
| \`/images\` | \`backend/app/api/v1/images.py\` | Docker images + pull |
| \`/files\` | \`backend/app/api/v1/files.py\` | Scan/read/write/upload |
| \`/demos\` | \`backend/app/api/v1/demos.py\` | Demo catalog + run |
| \`/events\` | \`backend/app/api/v1/events.py\` | SSE stream |
| \`/agent\` | \`backend/app/api/v1/agent.py\` | Conversations + traces |

## Key Modules
| Module | Purpose | Exports | Dependencies |
| --- | --- | --- | --- |
| \`backend/app/main.py\` | App setup + middleware | \`app\` | FastAPI, API router |
| \`backend/app/api/deps.py\` | DB session dependency | \`get_db\` | SQLAlchemy async |
| \`backend/app/services/agent/graph.py\` | Agent state graph | \`build_agent_graph\` | LangGraph, LLM clients |
| \`backend/app/services/agent/planner.py\` | Task decomposition | \`TaskPlanner\`, \`ExecutionPlan\` | LangChain LLM |
| \`backend/app/services/agent/executor.py\` | Plan execution | \`PlanExecutor\` | Planner, tools, events |
| \`backend/app/services/agent/tools/*\` | Tool registry (${backendData.tools.length} tools) | Tool classes | Repos, utils |
| \`backend/app/runtime/events.py\` | SSE event bus | \`publish_event\` | asyncio |
| \`backend/app/services/run_service.py\` | Run lifecycle + job dispatch | \`RunService\` | repos, runtime |
| \`backend/app/services/nextflow_service.py\` | Nextflow adapter | \`NextflowService\` | subprocess utils |
| \`backend/app/services/miniwdl_service.py\` | MiniWDL adapter | \`MiniWDLService\` | subprocess utils |
| \`backend/app/repositories/base.py\` | Generic CRUD + cursor pagination | \`BaseRepository\` | SQLAlchemy |
| \`backend/app/utils/responses.py\` | Standard response envelope | \`success_response\`, \`error_response\` | Pydantic schemas |

## Data Flow
- Requests enter \`api/v1/*\` routers, validate payloads with Pydantic schemas, then call services.
- Services coordinate repositories and workflow adapters; long-running work emits SSE events.
- Agent endpoints create conversations/messages, then stream LangGraph updates as SSE events.
- Complex tasks use TaskPlanner for decomposition and PlanExecutor for orchestrated execution.

## Statistics
- ${backendData.totalFiles} Python files
- ${backendData.apiRoutes.length} API routes
- ${backendData.services.length} services
- ${backendData.models.length} models
- ${backendData.repos.length} repositories
- ${backendData.schemas.length} schemas
- ${backendData.tools.length} agent tools
- ${backendData.tests.length} test files

## External Dependencies
- FastAPI, Uvicorn, Pydantic + pydantic-settings
- SQLAlchemy async + aiosqlite, Alembic
- LangGraph + LangChain (Anthropic/OpenAI/Gemini)
- Docker SDK, MiniWDL, psutil, structlog

## Related Areas
- [Architecture Codemap](architecture.md)
- [Data Codemap](data.md)
`,

  'frontend.md': `# Frontend Codemap
**Last Updated:** ${timestamp}
**Entry Points:** \`frontend/app/layout.tsx\`, \`frontend/app/(app)/layout.tsx\`, \`frontend/app/page.tsx\`, \`frontend/app/api/auth/[...all]/route.ts\`

## Architecture
\`\`\`
Next.js App Router
   │
   ├─ Landing pages (marketing)
   ├─ App routes (agent, runs, workflows, images)
   └─ Auth API routes (Better Auth)

Client data flow:
UI → apiRequest (lib/api.ts) → FastAPI
UI → useEvents (SSE) → EventBus
\`\`\`

## Routes (${frontendData.pages.length} pages)
| Route | File | Notes |
| --- | --- | --- |
| \`/\` | \`frontend/app/page.tsx\` | Marketing landing page |
| \`/auth\` | \`frontend/app/auth/page.tsx\` | Auth UI |
| \`/agent\` | \`frontend/app/(app)/agent/page.tsx\` | Agent chat |
| \`/images\` | \`frontend/app/(app)/images/page.tsx\` | Image inventory |
| \`/runs\` | \`frontend/app/(app)/runs/page.tsx\` | Run list + detail |
| \`/workflows\` | \`frontend/app/(app)/workflows/page.tsx\` | Workflow catalog |
| \`/api/auth/[...all]\` | \`frontend/app/api/auth/[...all]/route.ts\` | Better Auth handler |

## Key Modules
| Module | Purpose | Exports | Dependencies |
| --- | --- | --- | --- |
| \`frontend/lib/api.ts\` | API helper + envelope parsing | \`apiRequest\`, \`ApiError\` | Fetch, types |
| \`frontend/hooks/use-events.ts\` | SSE subscription | \`useEvents\` | EventSource |
| \`frontend/lib/conversations.ts\` | Local conversation storage | helpers | localStorage |
| \`frontend/components/bioinfoflow/chat-stream.tsx\` | Chat UI + agent actions | \`ChatStream\` | API + SSE |
| \`frontend/components/bioinfoflow/live-deck.tsx\` | Right sidebar panels | \`LiveDeck\` | UI primitives |
| \`frontend/components/bioinfoflow/dag-panel.tsx\` | Workflow DAG view | \`DagPanel\` | React Flow |
| \`frontend/components/bioinfoflow/plan-card.tsx\` | Plan visualization | \`PlanCard\` | UI primitives |
| \`frontend/components/landing/*\` | Marketing sections | Components | Framer Motion |
| \`frontend/components/ui/*\` | UI primitives | Components | Radix UI |

## Data Flow
- Pages call \`apiRequest\` for CRUD + agent actions using the API envelope.
- \`useEvents\` subscribes to \`/events/stream\` and dispatches status/trace updates to UI state.
- Auth routes are handled by Better Auth via \`/api/auth/[...all]\`.

## Statistics
- ${frontendData.totalFiles} TS/TSX files
- ${frontendData.pages.length} pages
- ${frontendData.layouts.length} layouts
- ${frontendData.components.length} components
- ${frontendData.hooks.length} hooks
- ${frontendData.lib.length} lib files
- ${frontendData.tests.length} test files

## External Dependencies
- Next.js 16, React 19, Radix UI
- Better Auth, agentation toolbar
- React Flow (DAG), Framer Motion
- Tailwind CSS 4

## Tests
- Playwright E2E specs in \`frontend/tests/e2e\`.

## Related Areas
- [Architecture Codemap](architecture.md)
- [Backend Codemap](backend.md)
`,

  'data.md': `# Data Codemap
**Last Updated:** ${timestamp}
**Entry Points:** \`backend/app/models/\`, \`backend/alembic/versions/*.py\`, \`backend/app/schemas/\`, \`frontend/lib/types.ts\`

## Architecture
\`\`\`
Pydantic Schemas ↔ FastAPI ↔ Repositories ↔ SQLAlchemy Models ↔ SQLite
                        │
                        └─ Frontend types mirror API envelopes
\`\`\`

## Database Tables (Alembic)
- \`projects\`
- \`workflows\`
- \`docker_images\`
- \`runs\`
- \`conversations\` (includes \`title\`, \`pinned\`)
- \`messages\`
- \`agent_traces\`

## ORM Models (backend/app/models)
| Model | Purpose | Key Fields |
| --- | --- | --- |
| \`Project\` | Workspace container | name, workspace_path |
| \`Workflow\` | Pipeline registry | source, engine, version |
| \`Run\` | Execution record | run_id, status, config |
| \`DockerImage\` | Image inventory | name, tag, status |
| \`Conversation\` | Agent thread | title, pinned |
| \`Message\` | Agent/user messages | role, type, metadata |
| \`AgentTrace\` | Tool/prompt traces | type, payload |

## API Schemas (backend/app/schemas)
- \`agent.py\`: conversation/message/trace payloads
- \`common.py\`: envelope + pagination
- \`demo.py\`: demo catalog + run responses
- \`file.py\`: file scan/read/write/upload
- \`image.py\`: image read + pull
- \`project.py\`: project CRUD
- \`run.py\`: run lifecycle + retry/resume
- \`workflow.py\`: workflow registry

## Frontend Types (frontend/lib/types.ts)
- API envelope + meta types
- Core domain types: \`Project\`, \`Workflow\`, \`Run\`, \`DockerImage\`
- Agent types: \`AgentMessageRead\`, \`AgentConversationRead\`, \`AgentTraceResponse\`
- SSE event shapes: \`RunStatusEvent\`, \`RunLogEvent\`, \`ImageProgressEvent\`, \`AgentTraceEvent\`
- Plan types: \`PlanStep\`, \`ExecutionPlan\`

## Data Flow
- API requests validate payloads with Pydantic schemas, persist via repositories, and return \`{success,data,error,meta}\` envelopes.
- Frontend types mirror backend schemas to keep UI compile-time safe.
- Plans are streamed as SSE events during execution.

## External Dependencies
- SQLAlchemy async + aiosqlite, Alembic migrations, Pydantic v2.

## Related Areas
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
`
};

// Write all codemaps
console.log('✅ Writing updated codemaps...\n');

for (const [filename, content] of Object.entries(codemaps)) {
  const filepath = path.join(CODEMAPS_DIR, filename);
  fs.writeFileSync(filepath, content);
  console.log(`  ✓ ${filename}`);
}

console.log('\n✨ Codemaps updated successfully!');
console.log(`\nStatistics:`);
console.log(`  Backend: ${backendData.totalFiles} files, ${backendData.tools.length} tools, ${backendData.tests.length} tests`);
console.log(`  Frontend: ${frontendData.totalFiles} files, ${frontendData.pages.length} pages, ${frontendData.components.length} components`);
