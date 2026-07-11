# Dependencies Codemap

**Last Updated:** 2026-07-11

## Backend Runtime

| Area | Declared packages |
| --- | --- |
| HTTP and config | FastAPI, Uvicorn, Pydantic, pydantic-settings, python-dotenv, httpx, httpx-sse |
| Persistence | SQLAlchemy async, aiosqlite, Alembic |
| Workflow execution | Docker SDK, MiniWDL, Nextflow executable integration, psutil |
| Agent and providers | LiteLLM, Anthropic SDK, OpenAI SDK, Hermes Agent |
| Remote and security | AsyncSSH, cryptography |
| CLI and files | Typer, Rich, python-multipart, aiofiles, tomli-w |
| Search and logging | duckduckgo-search, structlog |

LangGraph and LangChain packages are not declared dependencies of the current
backend. AgentCore uses its own explicit runtime loop, tool registry, and
provider layer.

## Frontend Runtime

| Area | Declared packages |
| --- | --- |
| Framework | Next.js 16, React 19, TypeScript |
| Auth and localization | Better Auth, better-sqlite3, next-intl |
| UI | Tailwind CSS 4, Radix UI packages, cmdk, class-variance-authority, Lucide adapter, LobeHub icons |
| Visualization | React Flow, uPlot, Framer Motion |
| Agent/file rendering | React Markdown, remark-gfm, Shiki, CodeMirror, XLSX |
| Terminal | xterm.js and fit addon |

## Development Tooling

- Backend: pytest, pytest-asyncio, pytest-cov, Ruff, Vulture, respx.
- Frontend: ESLint, Knip, Vitest, Testing Library, Playwright, jsdom.
- Package managers: `uv` for Python and Bun for the frontend.

## External Runtime Requirements

- Docker daemon for container-backed workflows and image management
- Nextflow and MiniWDL executables (bundled in the backend image; configurable locally)
- Optional NVIDIA runtime/toolkit for GPU visibility
- AI provider APIs or local provider endpoints
- SSH servers and backend-visible credentials for Remote Connections
- Optional container registries such as GHCR or Harbor

Use `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, and
`frontend/bun.lock` as the exact dependency sources.
