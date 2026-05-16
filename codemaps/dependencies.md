# Dependencies Codemap
<!-- Generated: 2026-05-16 | Token estimate: ~600 -->
**Last Updated:** 2026-05-16

## Backend (Python — pyproject.toml)

### Core
| Package | Purpose |
| --- | --- |
| FastAPI + Uvicorn | HTTP server + ASGI |
| Pydantic + pydantic-settings | Validation + config |
| SQLAlchemy[asyncio] + aiosqlite | Async ORM + SQLite driver |
| Alembic | Database migrations |

### LLM / Agent
| Package | Purpose |
| --- | --- |
| LangGraph | Older graph-based agent compatibility path |
| langchain-core | Base interfaces |
| langchain-anthropic | Anthropic wrapper (Claude) |
| langchain-openai | OpenAI wrapper |
| langchain-google-genai | Gemini wrapper |
| google-genai | Native Gemini SDK |

### Workflow Execution
| Package | Purpose |
| --- | --- |
| miniwdl >= 1.13.1 | WDL workflow runner |
| docker (SDK) | Docker API client |

### HTTP / Streaming
| Package | Purpose |
| --- | --- |
| httpx | Async HTTP client |
| httpx-sse >= 0.4 | SSE streaming support |

### CLI
| Package | Purpose |
| --- | --- |
| typer >= 0.15 | CLI framework (`bif` command) |
| rich >= 13.0 | Terminal formatting |

### Utilities
| Package | Purpose |
| --- | --- |
| structlog | Structured logging |
| psutil | CPU/mem/disk/GPU monitoring |
| python-multipart | Multipart form parsing |
| python-dotenv | .env loading |
| tomli-w >= 1.0 | TOML serialization |

### Dev / Test
| Package | Purpose |
| --- | --- |
| pytest + pytest-asyncio | Test framework |
| pytest-cov | Coverage |
| ruff | Lint + format |
| vulture >= 2.14 | Dead code detection |
| respx >= 0.22 | HTTP mocking |

## Frontend (TypeScript — package.json)

### Core
| Package | Version | Purpose |
| --- | --- | --- |
| next | 16.0.10 | App framework |
| react / react-dom | 19.2.0 | UI library |
| typescript | ^5 | Type system |

### UI Components
| Package | Purpose |
| --- | --- |
| @radix-ui/react-* (14 packages) | Headless accessible components |
| cmdk | Command palette |
| sonner | Toast notifications |
| lucide-react | Icon library |
| framer-motion | Animations |

### Styling
| Package | Purpose |
| --- | --- |
| tailwindcss + @tailwindcss/postcss | Utility CSS (v4.1.9) |
| tailwind-merge + clsx | Class merging |
| class-variance-authority | Component variants |
| tw-animate-css | Animation utilities |

### Data / Visualization
| Package | Purpose |
| --- | --- |
| reactflow | DAG visualization (v11.11.4) |
| react-markdown + remark-gfm | Markdown rendering |

### Terminal
| Package | Purpose |
| --- | --- |
| @xterm/xterm | Terminal emulator (v6) |
| @xterm/addon-fit | Responsive terminal sizing |

### Auth / i18n / Theme
| Package | Purpose |
| --- | --- |
| better-auth | Authentication framework (v1.4.17) |
| better-sqlite3 | Auth database |
| next-intl | Internationalization |
| next-themes | Dark/light mode |

### Analytics
| Package | Purpose |
| --- | --- |
| @vercel/analytics | Usage tracking |
| agentation | Agent observability (dev) |

### Dev / Test
| Package | Purpose |
| --- | --- |
| vitest + @vitest/coverage-v8 | Test runner (80% coverage) |
| @testing-library/react + jest-dom + user-event | Component testing |
| @playwright/test | E2E testing |
| jsdom | DOM environment |
| eslint + eslint-config-next | Linting |
| knip | Dead code detection |

## External Services
| Service | Integration | Config |
| --- | --- | --- |
| Anthropic API | Native SDK (default LLM) | `ANTHROPIC_API_KEY` |
| OpenAI API | Via LangChain | `OPENAI_API_KEY` |
| Google Gemini | Via LangChain + native SDK | `GEMINI_API_KEY` |
| OpenRouter | Via OpenAI-compatible endpoint | `OPENROUTER_API_KEY` |
| Ollama | Local LLM server | `OLLAMA_BASE_URL` |
| DeepSeek | API provider | `DEEPSEEK_API_KEY` |
| xAI (Grok) | API provider | `XAI_API_KEY` |
| Docker Engine | Socket API `/var/run/docker.sock` | `DOCKER_SOCKET` |
| Nextflow | Binary subprocess | `NEXTFLOW_BIN` |
| MiniWDL | Python import + binary | `MINIWDL_BIN` |
| LangSmith (optional) | Tracing | `LANGSMITH_API_KEY` |
| GitHub OAuth (optional) | Social login | `GITHUB_CLIENT_ID/SECRET` |
| Google OAuth (optional) | Social login | `GOOGLE_CLIENT_ID/SECRET` |

## Related Areas
- [Architecture Codemap](architecture.md)
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
