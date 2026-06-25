<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow</h1>

<p align="center">
  <em>面向 Nextflow 与 WDL 生信流程的 Agentic 本地控制台。</em>
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/discord-join-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/docs-view-3b82f6" alt="Docs" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/website-visit-111827" alt="Website" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="License: MIT" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

---

Bioinfoflow 是面向生信流程的本地优先控制平面。它可以运行在工作站或实验室服务器上，把项目数据放在统一的 `BIOINFOFLOW_HOME` 下，并提供共享 Web UI 来注册流程、提交运行、查看日志和检查结果。

Bioinfoflow 位于 Nextflow 与 WDL/MiniWDL 之上，提供持久化调度器、工作流感知的数据布局、浏览器终端、HTTP CLI，以及 AgentCore 运行时。AgentCore 可以帮助准备配置、检查项目文件、操作选中的 SSH 主机，并在审批机制下启动更高影响的操作。

> [!TIP]
> 三行启动：
>
> ```bash
> git clone https://github.com/your-org/bioinfoflow && cd bioinfoflow
> cp .env.example .env   # 设置 owner 账号；provider key 可登录后在 UI 中配置
> docker compose up -d --build
> ```
>
> 然后打开 <http://localhost:3000>。

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — 注册流程、配置输入、提交运行、查看实时 DAG" width="100%" />
</p>

---

## 功能特性

- **流程目录**：注册 Nextflow 和 WDL 流程后，可从 UI、CLI 或 AgentCore 工具提交运行。
- **统一数据布局**：使用一个 `BIOINFOFLOW_HOME` 管理项目数据、参考、共享数据库、上传、运行输入和输出。
- **运行工作台**：在一个页面中配置输入、提交运行、查看 DAG、跟踪日志并检查输出。
- **持久化调度器**：使用并发槽位、资源检查、重试策略、超时处理、清理和重启恢复来调度运行。
- **AgentCore 运行时**：通过聊天检查文件、管理项目和流程、运行已审批的平台操作，并操作选中的 SSH 连接。
- **远程连接**：保存 SSH profile，通过后端测试连接，流式运行短探针命令，并将选中的主机暴露给 AgentCore 工具。
- **浏览器终端和 `bif` CLI**：使用 Web UI 进行交互操作，使用 CLI 针对运行中的后端编写脚本。
- **本地认证和团队角色**：支持 personal、team 和 dev 三种认证模式，基于 Better Auth 管理会话。

---

## 快速开始

### 前置条件

- Docker Engine 或 Docker Desktop，并启用 Compose
- 一个用于 Agent 的 AI provider key。你可以登录后在 **Settings -> AI Providers** 里直接粘贴，也可以用 `.env` 做初始化 bootstrap。

### 用 Docker 启动

```bash
cp .env.example .env
```

编辑 `.env`，至少写入 owner 账号：

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

登录后进入 **Settings -> AI Providers**，OpenAI、Anthropic、Gemini、Grok、Groq、DeepSeek、OpenRouter 只需要粘贴 API key；Ollama、vLLM 和通用 OpenAI-compatible endpoint 也可以在同一页配置。无头部署时可用 `.env` 初始化，例如 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GEMINI_API_KEY`、`DEEPSEEK_API_KEY`、`OPENROUTER_API_KEY`、`XAI_API_KEY`、`GROK_API_KEY`、`GROQ_API_KEY`、`OLLAMA_BASE_URL`、`VLLM_BASE_URL`、`VLLM_API_KEY`、`VLLM_MODEL`、`OPENAI_COMPATIBLE_BASE_URL`、`OPENAI_COMPATIBLE_API_KEY` 和 `OPENAI_COMPATIBLE_MODEL`。

启动整套服务：

```bash
docker compose up -d --build
```

打开：

- **UI** — <http://localhost:3000>
- **API 文档** — <http://localhost:8000/api/v1/docs>

用 `.env` 里的 owner 邮箱和密码登录。

本地 Docker 部署最省心的做法是不要自己设 `BIOINFOFLOW_HOME` —— Compose 会把平台数据写入仓库里的 `data/` 目录，并在容器内挂载到相同的绝对路径。如果是共享或远程服务器，请在构建前设好 `BETTER_AUTH_SECRET`、`NEXT_PUBLIC_API_BASE_URL`、`BETTER_AUTH_URL`、`CORS_ORIGINS` 和 `TRUSTED_HOSTS`。详细配置见 [Docker Quick Start](docs/getting-started/docker.md) 和 [Runbook](RUNBOOK.md)。

### 使用已发布镜像启动

如果只是本机快速体验，可以直接拉取 GHCR 上的发布镜像，省掉本地构建：

```bash
cp .env.example .env
# 编辑 .env：填 owner credentials；provider key 可登录后在 UI 中配置
cat >> .env <<'EOF'
IMAGE_REGISTRY=ghcr.io/lewismessthecode
IMAGE_TAG=latest
EOF
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

发布镜像会在 `main` 上的后端或前端代码变化后刷新。当前发布版前端镜像面向 localhost 构建；如果要部署到远程服务器，请先在 `.env` 里设置公网 URL，再使用上面的源码构建方式。

---

## 本地开发

后端：

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```

前端：

```bash
cd frontend
bun install
bun run dev
```

常用检查：

```bash
cd backend  && uv run pytest && uv run ruff check .
cd frontend && bun run lint && bun run test
```

前后端默认都读仓库根目录的 `.env`，只在需要机器本地覆盖时才用 `backend/.env` 或 `frontend/.env.local`。

---

## CLI

`bif` 是面向运行中后端的 HTTP 客户端：

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

用 `--base-url` 或 `BIOFLOW_API_URL` 指向非默认后端。完整命令见 [CLI Reference](docs/reference/cli.md)。

---

## 文档

- [文档首页](docs/README.md)
- [Docker 快速开始](docs/getting-started/docker.md)
- [远程连接](docs/guides/remote-connections.md)
- [存储与数据布局](docs/concepts/storage.md)
- [CLI 参考](docs/reference/cli.md)
- [架构](docs/architecture.md)
- [安全说明](docs/security.md)
- [Runbook](RUNBOOK.md)

---

## License

Bioinfoflow 以 [MIT License](LICENSE) 发布。
