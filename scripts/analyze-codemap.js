#!/usr/bin/env node

/**
 * Codemap Analysis Script
 * Analyzes codebase structure and generates architecture documentation
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PROJECT_ROOT = path.join(__dirname, '..');
const CODEMAPS_DIR = path.join(PROJECT_ROOT, 'codemaps');
const REPORTS_DIR = path.join(PROJECT_ROOT, '.reports');

// Ensure directories exist
if (!fs.existsSync(REPORTS_DIR)) {
  fs.mkdirSync(REPORTS_DIR, { recursive: true });
}

/**
 * Scan directory for files matching patterns
 */
function scanFiles(dir, patterns, exclude = []) {
  const results = [];

  function scan(currentDir) {
    try {
      const entries = fs.readdirSync(currentDir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(currentDir, entry.name);
        const relativePath = path.relative(PROJECT_ROOT, fullPath);

        // Skip excluded paths
        if (exclude.some(ex => relativePath.includes(ex))) continue;

        if (entry.isDirectory()) {
          scan(fullPath);
        } else if (entry.isFile()) {
          if (patterns.some(p => entry.name.match(p))) {
            results.push(relativePath);
          }
        }
      }
    } catch (err) {
      // Skip permission errors
    }
  }

  scan(dir);
  return results;
}

/**
 * Extract imports from Python file
 */
function extractPythonImports(filePath) {
  try {
    const content = fs.readFileSync(path.join(PROJECT_ROOT, filePath), 'utf8');
    const imports = [];

    const importRegex = /^(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))/gm;
    let match;

    while ((match = importRegex.exec(content)) !== null) {
      const module = match[1] || match[2];
      if (module && !module.startsWith('.')) {
        imports.push(module.split('.')[0].trim());
      }
    }

    return [...new Set(imports)];
  } catch (err) {
    return [];
  }
}

/**
 * Extract imports from TypeScript/JavaScript file
 */
function extractTsImports(filePath) {
  try {
    const content = fs.readFileSync(path.join(PROJECT_ROOT, filePath), 'utf8');
    const imports = [];

    const importRegex = /import\s+.*?from\s+['"](.*?)['"]/g;
    let match;

    while ((match = importRegex.exec(content)) !== null) {
      const module = match[1];
      if (module && !module.startsWith('.') && !module.startsWith('@/')) {
        imports.push(module.split('/')[0]);
      }
    }

    return [...new Set(imports)];
  } catch (err) {
    return [];
  }
}

/**
 * Analyze backend structure
 */
function analyzeBackend() {
  const backendDir = path.join(PROJECT_ROOT, 'backend');

  // Scan Python files
  const pyFiles = scanFiles(backendDir, [/\.py$/], [
    'node_modules', '__pycache__', '.venv', 'venv', '.pytest_cache', 'alembic/versions'
  ]);

  // Group by directory
  const apiRoutes = pyFiles.filter(f => f.includes('app/api/v1/'));
  const services = pyFiles.filter(f => f.includes('app/services/'));
  const models = pyFiles.filter(f => f.includes('app/models/'));
  const repos = pyFiles.filter(f => f.includes('app/repositories/'));
  const schemas = pyFiles.filter(f => f.includes('app/schemas/'));
  const tools = pyFiles.filter(f => f.includes('app/services/agent/tools/'));
  const tests = pyFiles.filter(f => f.includes('tests/'));

  // Extract key dependencies
  const allImports = new Set();
  pyFiles.slice(0, 50).forEach(file => {
    extractPythonImports(file).forEach(imp => allImports.add(imp));
  });

  return {
    totalFiles: pyFiles.length,
    apiRoutes,
    services,
    models,
    repos,
    schemas,
    tools,
    tests,
    dependencies: Array.from(allImports).sort()
  };
}

/**
 * Analyze frontend structure
 */
function analyzeFrontend() {
  const frontendDir = path.join(PROJECT_ROOT, 'frontend');

  // Scan TS/TSX files
  const tsFiles = scanFiles(frontendDir, [/\.(ts|tsx)$/], [
    'node_modules', '.next', 'dist', 'build'
  ]);

  // Group by directory
  const pages = tsFiles.filter(f => f.includes('app/') && f.includes('page.tsx'));
  const layouts = tsFiles.filter(f => f.includes('app/') && f.includes('layout.tsx'));
  const components = tsFiles.filter(f => f.includes('components/'));
  const hooks = tsFiles.filter(f => f.includes('hooks/'));
  const lib = tsFiles.filter(f => f.includes('lib/'));
  const tests = tsFiles.filter(f => f.includes('tests/'));

  // Extract key dependencies
  const allImports = new Set();
  tsFiles.slice(0, 50).forEach(file => {
    extractTsImports(file).forEach(imp => allImports.add(imp));
  });

  return {
    totalFiles: tsFiles.length,
    pages,
    layouts,
    components,
    hooks,
    lib,
    tests,
    dependencies: Array.from(allImports).sort()
  };
}

/**
 * Calculate file size
 */
function getFileSize(filePath) {
  try {
    const stats = fs.statSync(path.join(PROJECT_ROOT, filePath));
    return stats.size;
  } catch {
    return 0;
  }
}

/**
 * Calculate diff percentage
 */
function calculateDiff(oldContent, newContent) {
  const oldLines = oldContent.split('\n').filter(l => l.trim());
  const newLines = newContent.split('\n').filter(l => l.trim());

  const maxLines = Math.max(oldLines.length, newLines.length);
  if (maxLines === 0) return 0;

  let differences = 0;
  for (let i = 0; i < maxLines; i++) {
    if (oldLines[i] !== newLines[i]) differences++;
  }

  return (differences / maxLines * 100).toFixed(1);
}

/**
 * Generate architecture codemap
 */
function generateArchitectureCodemap(backendData, frontendData) {
  const timestamp = new Date().toISOString().split('T')[0];

  return `# Architecture Codemap
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
`;
}

/**
 * Generate backend codemap
 */
function generateBackendCodemap(data) {
  const timestamp = new Date().toISOString().split('T')[0];

  return `# Backend Codemap
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
   │              ├─ Agent runtime (LangGraph + ${data.tools.length} tools)
   │              └─ Planning system (Planner + Executor)
   │
   └─ SSE EventBus (runtime/events.py)
\`\`\`

## API Routes (${data.apiRoutes.length} routes)
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
| \`backend/app/services/agent/tools/*\` | Tool registry (${data.tools.length} tools) | Tool classes | Repos, utils |
| \`backend/app/runtime/events.py\` | SSE event bus | \`publish_event\` | asyncio |
| \`backend/app/services/run_service.py\` | Run lifecycle + job dispatch | \`RunService\` | repos, runtime |
| \`backend/app/services/nextflow_service.py\` | Nextflow adapter | \`NextflowService\` | subprocess utils |
| \`backend/app/services/miniwdl_service.py\` | MiniWDL adapter | \`MiniWDLService\` | subprocess utils |
| \`backend/app/repositories/base.py\` | Generic CRUD + cursor pagination | \`BaseRepository\` | SQLAlchemy |
| \`backend/app/utils/responses.py\` | Standard response envelope | \`success_response\`, \`error_response\` | Pydantic schemas |

## Agent Tools (${data.tools.length})
${data.tools.slice(0, 15).map(t => `- \`${t}\``).join('\n')}

## Data Flow
- Requests enter \`api/v1/*\` routers, validate payloads with Pydantic schemas, then call services.
- Services coordinate repositories and workflow adapters; long-running work emits SSE events.
- Agent endpoints create conversations/messages, then stream LangGraph updates as SSE events.
- Complex tasks use TaskPlanner for decomposition and PlanExecutor for orchestrated execution.

## Statistics
- ${data.totalFiles} Python files
- ${data.apiRoutes.length} API routes
- ${data.services.length} services
- ${data.models.length} models
- ${data.repos.length} repositories
- ${data.schemas.length} schemas
- ${data.tools.length} agent tools
- ${data.tests.length} test files

## External Dependencies
${data.dependencies.slice(0, 30).map(d => `- ${d}`).join('\n')}

## Related Areas
- [Architecture Codemap](architecture.md)
- [Data Codemap](data.md)
`;
}

/**
 * Generate frontend codemap
 */
function generateFrontendCodemap(data) {
  const timestamp = new Date().toISOString().split('T')[0];

  return `# Frontend Codemap
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

## Routes (${data.pages.length} pages)
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

## Component Breakdown
${data.components.slice(0, 20).map(c => `- \`${c}\``).join('\n')}

## Data Flow
- Pages call \`apiRequest\` for CRUD + agent actions using the API envelope.
- \`useEvents\` subscribes to \`/events/stream\` and dispatches status/trace updates to UI state.
- Auth routes are handled by Better Auth via \`/api/auth/[...all]\`.

## Statistics
- ${data.totalFiles} TS/TSX files
- ${data.pages.length} pages
- ${data.layouts.length} layouts
- ${data.components.length} components
- ${data.hooks.length} hooks
- ${data.lib.length} lib files
- ${data.tests.length} test files

## External Dependencies
${data.dependencies.slice(0, 30).map(d => `- ${d}`).join('\n')}

## Tests
- Playwright E2E specs in \`frontend/tests/e2e\`.

## Related Areas
- [Architecture Codemap](architecture.md)
- [Backend Codemap](backend.md)
`;
}

/**
 * Generate data codemap
 */
function generateDataCodemap() {
  const timestamp = new Date().toISOString().split('T')[0];

  return `# Data Codemap
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
`;
}

/**
 * Main execution
 */
function main() {
  console.log('🔍 Analyzing codebase structure...\n');

  // Analyze structure
  const backendData = analyzeBackend();
  const frontendData = analyzeFrontend();

  console.log(`📊 Backend: ${backendData.totalFiles} files`);
  console.log(`📊 Frontend: ${frontendData.totalFiles} files\n`);

  // Generate new codemaps
  const codemaps = {
    'architecture.md': generateArchitectureCodemap(backendData, frontendData),
    'backend.md': generateBackendCodemap(backendData),
    'frontend.md': generateFrontendCodemap(frontendData),
    'data.md': generateDataCodemap()
  };

  // Calculate diffs
  const diffs = {};
  const report = [];

  report.push('# Codemap Diff Report');
  report.push(`Generated: ${new Date().toISOString()}\n`);

  for (const [filename, newContent] of Object.entries(codemaps)) {
    const filepath = path.join(CODEMAPS_DIR, filename);

    if (fs.existsSync(filepath)) {
      const oldContent = fs.readFileSync(filepath, 'utf8');
      const diffPercent = calculateDiff(oldContent, newContent);
      diffs[filename] = parseFloat(diffPercent);

      report.push(`## ${filename}`);
      report.push(`Diff: ${diffPercent}%`);
      report.push('');
    } else {
      diffs[filename] = 100;
      report.push(`## ${filename}`);
      report.push('Status: NEW');
      report.push('');
    }
  }

  // Calculate average diff
  const avgDiff = Object.values(diffs).reduce((a, b) => a + b, 0) / Object.values(diffs).length;

  report.unshift(`Average diff: ${avgDiff.toFixed(1)}%\n`);

  // Save report
  const reportPath = path.join(REPORTS_DIR, 'codemap-diff.txt');
  fs.writeFileSync(reportPath, report.join('\n'));

  console.log('📝 Diff Report:');
  console.log(`Average change: ${avgDiff.toFixed(1)}%\n`);

  for (const [filename, diff] of Object.entries(diffs)) {
    console.log(`  ${filename}: ${diff}%`);
  }

  console.log(`\n📄 Full report: ${reportPath}`);

  // Check if approval needed
  if (avgDiff > 30) {
    console.log('\n⚠️  Changes exceed 30% threshold - approval required');
    console.log('Updated codemaps saved to memory (not written to disk)');

    // Output new content for review
    console.log('\n--- NEW CONTENT PREVIEW ---\n');
    console.log(codemaps['architecture.md'].split('\n').slice(0, 15).join('\n'));
    console.log('\n...(truncated)\n');

    process.exit(2); // Special exit code for approval needed
  }

  // Write updated codemaps
  for (const [filename, content] of Object.entries(codemaps)) {
    const filepath = path.join(CODEMAPS_DIR, filename);
    fs.writeFileSync(filepath, content);
    console.log(`✅ Updated ${filename}`);
  }

  console.log('\n✨ Codemaps updated successfully!');
}

// Run
try {
  main();
} catch (error) {
  console.error('❌ Error:', error.message);
  process.exit(1);
}
