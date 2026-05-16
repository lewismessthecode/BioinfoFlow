<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow 👋</h1>

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

生物信息学的工具体验长期停在上个时代——界面陈旧、操作繁琐、学习曲线陡到劝退。

Bioinfoflow 想做的事很直接：把现代软件工程的优雅带进生物信息学，再让 AI Agent 弥合生物学与计算机科之间的鸿沟。

Bioinfoflow 基于 Nextflow 与 WDL 之上：流程注册一次，项目数据收进同一个 `BIOINFOFLOW_HOME`，运行交给统一调度，DAG、日志、资源压力与产出都在同一界面里。

最终愿景：作为在计算层之上统一的产品界面，让计算生物学人人可用——用自然语言，进行生物信息学分析。

**配一张 16GB 显存以上的显卡（如 RTX 4080），在家就足以跑通 Parabricks 的 WGS 流程，亲手解读自己的基因组。**

> [!TIP]
> 三行启动：
>
> ```bash
> git clone https://github.com/your-org/bioinfoflow && cd bioinfoflow
> cp .env.example .env   # 在 .env 里填入 ANTHROPIC_API_KEY（或其他 provider 的 key）
> docker compose up -d --build
> ```
>
> 然后打开 <http://localhost:3000>。

<!--
  Hero 视频：把下面这段 <img> 换成 GitHub CDN 托管的 mp4，渲染清晰度最佳。
  步骤：
    1. 在本仓库新建一条 issue/PR draft（不必提交）
    2. 把 assets/product-preview.mp4 拖进评论框，等待上传完成
    3. 复制生成的 https://github.com/user-attachments/assets/<uuid> 链接
    4. 替换为：<video src="<上一步的链接>" autoplay loop muted playsinline width="100%"></video>
-->
<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — 注册流程、配置输入、提交运行、查看实时 DAG" width="100%" />
</p>

---

## ⭐ 功能特性

- 🧬 **流程目录** — 一处注册，随处运行；nf-core/rnaseq、Parabricks WGS 等流程开箱即用。
- 📁 **统一数据布局** — 一个 `BIOINFOFLOW_HOME` 装下项目文件、参考、数据库、上传与产出。
- 🚦 **运行工作台** — 配置、提交、追踪实时 DAG、查看日志与产出，全在同一页面完成。
- ⚙️ **持久化调度器** — 任务排队不丢、资源不够不开跑、跑挂了自动重试。
- 🤖 **AI Agent** — 用聊天的方式注册流程、准备配置、检查文件、提交运行、解读结果。
- 💻 **浏览器终端 与 `bif` CLI** — 想用界面就用界面，想用 shell 就用 shell。
- 🔐 **本地认证与个性化** — 个人或团队模式自由切换，多套主题一键换肤。

<!--
  TODO（方案 3）：在此处加 2–3 张功能子截图，做"满屏证据感"。
  建议三张：
    - workflow catalog 页（侧栏 + 流程卡片）
    - run 详情页（实时 DAG + 日志侧栏）
    - agent 对话页（含一次审批流程）
  尺寸：1600px 宽 PNG，单图 < 800KB（pngquant 压一下）。
  排布建议：
    <p align="center">
      <img src="assets/feature-catalog.png"  width="32%" />
      <img src="assets/feature-run-dag.png"  width="32%" />
      <img src="assets/feature-agent.png"    width="32%" />
    </p>
-->

---

## 🚀 快速开始

### 前置条件

- Docker Engine 或 Docker Desktop，并启用 Compose
- 一个 AI provider key（Anthropic、OpenAI、Gemini、DeepSeek，或兼容 OpenAI API 的 provider）

### 用 Docker 启动

```bash
cp .env.example .env
```

编辑 `.env`，至少写入：

```env
ANTHROPIC_API_KEY=...
# 或 OPENAI_API_KEY=... / GEMINI_API_KEY=... / DEEPSEEK_API_KEY=...

AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

启动整套服务：

```bash
docker compose up -d --build
```

打开：

- **UI** — <http://localhost:3000>
- **API 文档** — <http://localhost:8000/api/v1/docs>

用 `.env` 里的 owner 邮箱和密码登录。

本地 Docker 部署最省心的做法是不要自己设 `BIOINFOFLOW_HOME` —— Compose 会把平台数据写入仓库里的 `data/` 目录，并在容器内挂载到相同的绝对路径。如果是共享或远程服务器，请在构建前设好 `BETTER_AUTH_SECRET`、`NEXT_PUBLIC_API_BASE_URL`、`BETTER_AUTH_URL`、`CORS_ORIGINS` 和 `TRUSTED_HOSTS`。详细配置见 [Docker Quick Start](docs/getting-started/docker.md) 和 [Runbook](RUNBOOK.md)。

---

## 🛠 本地开发

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

## 💻 CLI

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

## 📚 文档

- [文档首页](docs/README.md)
- [Docker 快速开始](docs/getting-started/docker.md)
- [存储与数据布局](docs/concepts/storage.md)
- [CLI 参考](docs/reference/cli.md)
- [架构](docs/architecture.md)
- [安全说明](docs/security.md)
- [Runbook](RUNBOOK.md)

---

## 📜 License

Bioinfoflow 以 [MIT License](LICENSE) 发布。
