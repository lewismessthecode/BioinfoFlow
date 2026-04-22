# Contributing Guide

**Last Updated:** 2026-02-04
**Source of Truth:** `backend/pyproject.toml`, `frontend/package.json`, `backend/.env.example`

This guide provides everything you need to contribute to Bioinfoflow.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Available Scripts](#available-scripts)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Style](#code-style)
- [Git Workflow](#git-workflow)

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd bioinfo-agent-pipe

# 2. Backend setup
cd backend
uv sync                                    # Install dependencies
cp .env.example .env                       # Configure environment
uv run alembic upgrade head                # Apply migrations
uv run uvicorn app.main:app --reload --port 8000  # Start dev server

# 3. Frontend setup (in new terminal)
cd frontend
bun install                                # Install dependencies
bun run dev                                # Start dev server (port 3000)
```

Visit `http://localhost:3000` - the frontend will proxy API requests to `http://localhost:8000`.

---

## Development Environment

### Prerequisites

**Backend:**
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for containerized workflows)
- Nextflow and/or MiniWDL (optional, for workflow execution)

**Frontend:**
- Node.js 18+
- [Bun](https://bun.sh) runtime and package manager

### Environment Variables

Copy `backend/.env.example` to `backend/.env` and configure:

#### Application Settings
```bash
APP_NAME=Bioinfoflow                      # Application name
DEBUG=false                                # Debug mode (true for development)
WORKFLOW_REGISTRY_ROOT=~/.bioinfoflow/workflows  # Workflow storage path
REPO_ROOT=                                 # Optional repository root override
```

#### Database (SQLite)
```bash
DATABASE_URL=sqlite+aiosqlite:///./bioinfoflow.db  # SQLite connection string
```

#### Workflow Engines
```bash
# Nextflow configuration
NEXTFLOW_BIN=/usr/local/bin/nextflow      # Nextflow binary path
NEXTFLOW_WORK_DIR=/tmp/bioinfoflow/work   # Nextflow working directory

# MiniWDL configuration
MINIWDL_BIN=/usr/local/bin/miniwdl        # MiniWDL binary path
MINIWDL_WORK_DIR=/tmp/bioinfoflow/miniwdl # MiniWDL working directory
```

#### Docker
```bash
DOCKER_SOCKET=unix:///var/run/docker.sock  # Docker daemon socket
```

#### Agent / LLM Configuration
```bash
# Provider selection (auto-detects from available API keys)
AGENT_PROVIDER=auto                        # Options: auto, anthropic, openai, gemini

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...              # Anthropic API key
ANTHROPIC_MODEL=claude-sonnet-4-5         # Model to use
ANTHROPIC_DISABLED=false                   # Disable Anthropic provider

# Google Gemini
GEMINI_API_KEY=your-gemini-key            # Gemini API key
GEMINI_MODEL=gemini-2.5-flash             # Model to use

# OpenAI
OPENAI_API_KEY=                            # OpenAI API key (optional)
OPENAI_BASE_URL=https://api.openai.com/v1 # API endpoint
OPENAI_MODEL=gpt-4o-mini                  # Model to use

# Agent behavior
AGENT_MODEL=claude-sonnet-4-5             # Default model override
AGENT_MAX_TOKENS=4096                      # Max tokens per request
AGENT_OBSERVABILITY=false                  # Enable observability logging
AGENT_LOG_TRUNCATE_CHARS=1200             # Log truncation length

# LangSmith tracing (optional)
LANGSMITH_TRACING=false                    # Enable LangSmith tracing
LANGSMITH_API_KEY=                         # LangSmith API key
LANGSMITH_PROJECT=bioinfoflow             # Project name
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

#### CORS
```bash
CORS_ORIGINS=["http://localhost:3000"]    # Allowed CORS origins (JSON array)
```

---

## Available Scripts

### Backend (Python + uv)

| Script | Command | Description |
|--------|---------|-------------|
| **Development** | | |
| Start dev server | `uv run uvicorn app.main:app --reload --port 8000` | Start FastAPI with hot reload |
| Install dependencies | `uv sync` | Install all dependencies from pyproject.toml |
| Install dev dependencies | `uv sync --all-extras` | Install with dev dependencies |
| **Database** | | |
| Run migrations | `uv run alembic upgrade head` | Apply latest database migrations |
| Create migration | `uv run alembic revision --autogenerate -m "message"` | Generate new migration |
| Rollback migration | `uv run alembic downgrade -1` | Rollback last migration |
| Initialize database | `uv run python scripts/init_db.py` | Initialize database with seed data |
| **Testing** | | |
| Run all tests | `uv run pytest` | Run all tests with coverage |
| Run specific test | `uv run pytest tests/test_file.py -v` | Run specific test file |
| Run test directory | `uv run pytest tests/test_agent/ -v` | Run all tests in directory |
| Run with coverage | `uv run pytest --cov=app --cov-report=html` | Generate coverage report |
| **Code Quality** | | |
| Lint | `uv run ruff check .` | Check code style with ruff |
| Format | `uv run ruff format .` | Auto-format code |
| Find dead code | `uv run vulture app` | Detect unused code |
| **Docker** | | |
| Build container | `docker compose build` | Build backend container |
| Run container | `docker compose up` | Run containerized backend |
| Stop container | `docker compose down` | Stop containers |

### Frontend (TypeScript + Bun)

| Script | Command | Description |
|--------|---------|-------------|
| **Development** | | |
| Start dev server | `bun run dev` | Start Next.js dev server (port 3000) |
| Install dependencies | `bun install` | Install all dependencies |
| **Build** | | |
| Production build | `bun run build` | Build optimized production bundle |
| Start production | `bun run start` | Start production server |
| **Code Quality** | | |
| Lint | `bun run lint` | Run ESLint |
| **Testing** | | |
| Run E2E tests | `bun run test:e2e` | Run Playwright E2E tests |
| Playwright UI | `bun run test:e2e:ui` | Open Playwright UI |
| **Analysis** | | |
| Find unused code | `bunx knip` | Detect unused exports |
| Check unused deps | `bunx depcheck` | Find unused dependencies |
| Prune TS exports | `bunx ts-prune` | Find unused TypeScript exports |

---

## Development Workflow

### 1. Branch Strategy

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Create bugfix branch
git checkout -b fix/bug-description
```

### 2. Make Changes

- Follow [Code Style](#code-style) guidelines
- Write tests for new features
- Update documentation as needed

### 3. Test Your Changes

```bash
# Backend tests
cd backend
uv run pytest                              # All tests
uv run pytest tests/test_agent/ -v        # Agent tests only
uv run ruff check .                        # Linting

# Frontend tests
cd frontend
bun run lint                               # Linting
bun run build                              # Verify build works
```

### 4. Commit

Follow conventional commit format:

```bash
git commit -m "feat: add user authentication"
git commit -m "fix: resolve agent timeout issue"
git commit -m "docs: update API reference"
git commit -m "test: add workflow validation tests"
```

Commit types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Create a pull request with:
- Clear description of changes
- Link to related issues
- Screenshots (if UI changes)
- Test plan/checklist

---

## Testing

### Test Coverage Requirements

**Minimum: 80% coverage** across all new code.

### Backend Testing

**Test Types:**
1. **Unit Tests** - Test individual functions/classes
2. **Integration Tests** - Test API endpoints with database
3. **E2E Tests** - Test complete workflows

**Running Tests:**

```bash
cd backend

# All tests with coverage
uv run pytest --cov=app --cov-report=html

# Specific test suites
uv run pytest tests/test_agent/                    # Agent tests
uv run pytest tests/test_api/                      # API tests
uv run pytest tests/test_services/                 # Service tests

# Single test file
uv run pytest tests/test_agent/test_planner.py -v

# Single test function
uv run pytest tests/test_agent/test_planner.py::test_task_decomposition -v

# View coverage report
open htmlcov/index.html
```

**Test Organization:**
- `tests/test_api/` - API endpoint tests
- `tests/test_agent/` - Agent tool and planning tests
- `tests/test_services/` - Business logic tests
- `tests/test_repositories/` - Data access tests

### Frontend Testing

**Test Types:**
1. **E2E Tests** - Playwright tests for critical user flows

**Running Tests:**

```bash
cd frontend

# Run E2E tests
bun run test:e2e

# Run with UI
bun run test:e2e:ui

# Run specific test
bunx playwright test tests/e2e/auth.spec.ts
```

### Writing Tests

**Backend Example (pytest):**

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    """Test project creation endpoint."""
    payload = {"name": "Test Project", "workspace_path": "/tmp/test"}
    response = await client.post("/api/v1/projects", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Test Project"
```

**Frontend Example (Playwright):**

```typescript
import { test, expect } from '@playwright/test';

test('user can sign in', async ({ page }) => {
  await page.goto('/auth');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password123');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL('/agent');
});
```

---

## Code Style

### Python (Backend)

**Tool:** Ruff (formatting + linting)

**Rules:**
- Line length: 88 characters
- Quote style: Double quotes
- Python version: 3.13+

**Key Principles:**
- **Immutability:** Always create new objects, never mutate
- **Type hints:** Use type annotations for function signatures
- **Async/await:** Use async patterns consistently
- **Error handling:** Comprehensive error handling with proper exceptions

**Example:**

```python
from typing import Optional
from pydantic import BaseModel

class UserUpdate(BaseModel):
    """User update request."""
    name: Optional[str] = None
    email: Optional[str] = None

async def update_user(user_id: int, update: UserUpdate) -> User:
    """Update user record (immutable)."""
    user = await get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Immutable update - create new object
    updated_data = {**user.dict(), **update.dict(exclude_unset=True)}
    return User(**updated_data)
```

**Format code:**
```bash
uv run ruff format .
uv run ruff check --fix .
```

### TypeScript (Frontend)

**Tool:** ESLint + Next.js config

**Key Principles:**
- **Immutability:** Use const, avoid mutations
- **Type safety:** Leverage TypeScript fully
- **Functional components:** Use React hooks
- **Error boundaries:** Proper error handling

**Example:**

```typescript
interface User {
  id: string;
  name: string;
  email: string;
}

// Immutable update
function updateUserName(user: User, newName: string): User {
  return {
    ...user,
    name: newName, // Immutable - creates new object
  };
}

// React component
export function UserProfile({ userId }: { userId: string }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    fetchUser(userId).then(setUser);
  }, [userId]);

  if (!user) return <div>Loading...</div>;

  return <div>{user.name}</div>;
}
```

**Lint code:**
```bash
bun run lint
```

### General Guidelines

1. **Small files:** 200-400 lines typical, 800 max
2. **Small functions:** <50 lines preferred
3. **No deep nesting:** Max 4 levels
4. **Descriptive names:** Clear, unambiguous naming
5. **No console.log:** Use proper logging (structlog/logger)
6. **Comprehensive error handling:** Never swallow errors

---

## Git Workflow

### Commit Message Format

```
<type>: <description>

<optional body>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `test` - Test additions/changes
- `refactor` - Code refactoring
- `perf` - Performance improvements
- `chore` - Maintenance tasks
- `ci` - CI/CD changes

**Examples:**
```
feat: add multi-step agent planning system
fix: resolve SSE event ordering issue
docs: update contributor guide with testing section
test: add integration tests for workflow service
```

### Pull Request Process

1. **Create PR** with clear title and description
2. **Link issues** using "Fixes #123" or "Closes #456"
3. **Add labels** (feature, bugfix, docs, etc.)
4. **Request review** from maintainers
5. **Address feedback** and update PR
6. **Squash and merge** once approved

### PR Checklist

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated (if needed)
- [ ] No console.log statements
- [ ] No hardcoded secrets
- [ ] Commit messages follow convention
- [ ] PR description is clear and complete

---

## Architecture Overview

See [Architecture Codemap](../codemaps/architecture.md) for full details.

**Backend:** FastAPI + SQLAlchemy + LangGraph agent runtime
**Frontend:** Next.js 16 + React 19 + Radix UI
**Database:** SQLite (async with aiosqlite)
**Agent:** LangGraph with multi-step planning (Anthropic/OpenAI/Gemini)

**Key Directories:**
- `backend/app/api/v1/` - REST API endpoints
- `backend/app/services/` - Business logic
- `backend/app/services/agent/` - Agent runtime (LangGraph + tools)
- `backend/app/repositories/` - Data access layer
- `frontend/app/` - Next.js pages
- `frontend/components/` - React components
- `frontend/lib/` - Utilities and API client

---

## Getting Help

- **Documentation:** Check `docs/` directory and codemaps
- **Issues:** Search existing issues or create new one
- **Code review:** Ask questions in PR comments
- **Architecture:** Review `codemaps/` for system design

## License

See [LICENSE](../LICENSE) file for details.
