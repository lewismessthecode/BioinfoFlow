<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow</h1>

<p align="center">
  <em>一个让 Agent 真正参与生物信息分析的工作空间。</em>
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

一次生物信息分析，很少只是一条命令。流程文件、样本表、参考数据、容器镜像、运行日志、结果目录，以及解释这次分析为何这样执行的记录，常常散落在不同终端和文件夹里。

Bioinfoflow 想做的，是为这些工作提供一个稳定的归处。它把项目、分析流程、运行记录、DAG、日志、结果和终端放进同一套系统，也能同时接入平台管理的数据、已有本地目录和通过 SSH 连接的远程项目。Web 界面、`bif` CLI 与 Agent 使用的是同一个后端，系统则运行在你掌握的基础设施上。

Agent 不是附加在界面旁边的聊天窗口。它与平台共享真实的工作上下文：项目文件、流程定义、运行历史、调度状态、工具、技能，以及经过选择的远程主机。它可以在这些信息之上理解问题、查找证据、准备配置并采取行动；权限与审批机制则把重要操作的最终决定权留给人。

> [!TIP]
> 使用 Docker 在本机启动：
>
> ```bash
> git clone https://github.com/lewismessthecode/BioinfoFlow.git
> cd BioinfoFlow
> cp .env.example .env
> # 编辑 .env，修改初始所有者账号和密码
> docker compose up -d --build
> ```
>
> 然后打开 <http://localhost:3000>。

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — 注册分析流程、选择输入、提交运行并查看 DAG" width="100%" />
</p>

## 它把哪些事情放到了一起

### 让项目成为长期上下文

每个项目都有清楚的文件边界、流程绑定、运行历史和结果目录。项目数据既可以统一放在 `BIOINFOFLOW_HOME` 下由 Bioinfoflow 管理，也可以接入已有的本地目录；远程项目则可以绑定保存过的 SSH 连接。

### 让一次运行可以被追溯

分析流程注册一次后，便可以从 Web 界面、CLI 或 Agent 配置输入并提交运行。持久化调度器负责整次运行的并发、资源检查、重试、超时、清理和重启恢复；DAG、日志、事件、输入、审计记录与最终结果则保留在同一个运行工作区中。

目前的流程执行由 Nextflow 和 WDL/MiniWDL 适配器承担。这些引擎位于统一的项目与运行模型之后，是执行层的选择，而不是几套彼此割裂的使用方式。

### 让 Agent 不只回答，也能工作

Agent 使用的不是一段孤立的聊天记录，而是平台本身掌握的项目文件、分析流程、运行记录、调度资源、容器镜像、技能说明和远程连接。它可以从理解需求继续走向检查证据、准备配置、调用工具和提交任务。查看与整理工作可以直接进行；可能产生明显影响的操作，则受到权限和审批策略约束。

### 让本地与远程各守边界

浏览器终端、`bif` CLI 和远程连接覆盖了交互式与脚本化操作，但平台的重心仍然留在自有基础设施上。保存的 SSH 配置可用于连接测试、短命令探测、远程项目终端，以及范围受限的 Agent 工具。

这里所说的“本地优先”，强调的是数据与系统由谁掌握，并不意味着所有文件和计算资源都必须位于同一台机器。平台状态可以留在近处，同时按明确边界接入远程资源。

## 它适合谁

如果你有以下需要，Bioinfoflow 会比较合适：

- 在自己的计算资源上开发或维护生物信息分析流程；
- 希望终端关闭以后，一次运行仍然可以被理解、复查和复现；
- 希望项目、输入、日志、DAG 和结果不再分散在不同工具里；
- 希望 Agent 能依据真实的系统状态开展工作，同时把重要操作的决定权留给人。

Bioinfoflow 首先面向独立研究者、生信开发者，以及管理工作站、实验室服务器或 SSH 计算资源的小型团队。它不是托管式数据分析服务，也不要求把研究数据交给外部平台。

## 快速开始

### 环境要求

- Docker Engine 或 Docker Desktop，并启用 Compose
- 只有使用 Agent 时才需要配置 AI 服务：可以使用托管服务的 API key，也可以连接 Ollama、vLLM 或兼容 OpenAI 接口的本地服务

### 从源码启动

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
cp .env.example .env
```

在 `.env` 中设置初始所有者账号：

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

启动应用：

```bash
docker compose up -d --build
```

打开：

- Web 界面：<http://localhost:3000>
- API 文档：<http://localhost:8000/api/v1/docs>

从源码在本机启动时，数据默认保存在仓库的 `data/` 目录。登录后可以在 **设置 → AI 服务商** 中配置 Agent 使用的模型。发布镜像、GPU、私有镜像仓库和远程部署等内容，请参阅 [Docker 指南](docs/getting-started/docker.md)；环境变量的优先级和常见故障，请参阅 [运行手册](RUNBOOK.md)。

<details>
<summary>改用已经发布的镜像</summary>

已发布的前端镜像主要用于 localhost 下的个人模式体验。

```bash
cp .env.example .env
cat >> .env <<'EOF'
IMAGE_REGISTRY=ghcr.io/lewismessthecode
IMAGE_TAG=latest
EOF
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

如果需要远程访问地址、团队模式或不同的认证设置，请从源码构建。

</details>

## 工作原理

```text
Web 界面 / bif CLI / Agent
        ↓
FastAPI 服务与持久化状态
        ↓
调度器与流程引擎适配器
        ↓
运行在自有基础设施上的容器、日志、事件与结果
```

- 前端使用 Next.js，提供项目、分析流程、运行记录、镜像、远程连接、调度、设置、终端和 Agent 会话等界面。
- FastAPI 后端负责业务逻辑、持久化状态、存储路径、调度、执行、事件和工具调用。
- 流程引擎适配器把统一的运行模型转换为具体引擎的执行方式，并负责收集结果。
- `BIOINFOFLOW_HOME` 是平台状态、托管项目、流程源码、共享输入、缓存和结果的共同根目录。

更完整的实现边界见[架构概览](docs/architecture.md)和[架构参考](docs/reference/architecture.md)。

## 命令行

`bif` 是面向运行中 Bioinfoflow 后端的 HTTP 客户端：

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

可以使用 `--base-url` 或 `BIOFLOW_API_URL` 选择其他后端。完整命令见 [CLI 参考](docs/reference/cli.md)。

## 本地开发

```bash
# 后端
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000

# 在另一个终端中启动前端
cd frontend
bun install
bun run dev
```

后端检查使用 `uv run pytest && uv run ruff check .`，前端检查使用 `bun run lint && bun run test`。

## 使用边界

- Bioinfoflow 面向可信的机器和网络。Docker 部署会挂载 Docker socket，这意味着后端拥有主机级的容器控制能力。
- 分析流程使用同路径挂载：主机、后端、流程运行器和任务容器需要以一致的绝对路径看到相关数据。
- 远程连接用于查看文件、诊断问题、Agent 工具和交互式终端。分析任务仍由本地调度器和流程引擎适配器发起，而不是通过 SSH 调度。
- 面向团队或互联网开放时，需要显式配置密钥、可信来源、TLS、备份，并做好常规的基础设施加固。

在可信的本地环境之外部署前，请阅读[安全说明](docs/security.md)、[存储模型](docs/concepts/storage.md)和[运维手册](docs/operations/runbook.md)。

## 文档

- [文档首页](docs/README.md)
- [Docker 快速开始](docs/getting-started/docker.md)
- [运行手册](RUNBOOK.md)
- [架构说明](docs/architecture.md)
- [存储与数据布局](docs/concepts/storage.md)
- [远程连接](docs/guides/remote-connections.md)
- [nf-core/rnaseq 示例](demo/nfcore-rnaseq/README.md)

## 许可证

Bioinfoflow 以 [MIT License](LICENSE) 发布。
