<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">Bioinfoflow</h1>

<p align="center">
  <strong>让 Agent 真正看得见、跑得动你的生信工作流。</strong>
</p>

<p align="center">
  不用再把文件片段、报错和命令来回复制到聊天框里。Agent 可以直接查看项目文件、
  准备输入、运行 Nextflow 或 WDL、跟踪日志和 DAG，并结合完整上下文解释结果。
  整个平台仍然运行在你自己的基础设施上。
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/Discord-加入社区-5865F2?logo=discord&logoColor=white" alt="加入 Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/文档-查看-3b82f6" alt="查看文档" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/官网-访问-111827" alt="访问官网" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/开源协议-MIT-22c55e" alt="MIT License" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow Agent 检查工作流、提交任务并跟踪 DAG" width="100%" />
</p>

## 什么时候值得用 Bioinfoflow？

如果你只需要执行一条 Nextflow 或 MiniWDL 命令，现有工具可能已经够用。

Bioinfoflow 更适合另一种情况：命令不难，难的是把样本、参数、容器、工作目录、
运行记录、日志和结果始终放在同一个上下文里。尤其是任务失败以后，你还需要知道
它为什么失败、能不能安全重试，以及这批结果究竟是怎么得到的。

| 你可能会喜欢 Bioinfoflow，如果你…… | 它可能不适合你，如果你…… |
| --- | --- |
| 在自己的工作站、服务器或计算资源上开发和运行生信工作流 | 已经习惯只用工作流引擎和目录管理全部内容 |
| 希望关掉终端以后，仍然能追溯一次运行发生了什么 | 想要开箱即用的托管分析服务 |
| 想在一个地方查看文件、输入、DAG、日志和结果 | 需要开箱即用的多租户平台，并且不想自己运维 |
| 希望 Agent 能查看真实项目状态，但关键操作仍由人确认 | 希望 Agent 不经确认就能自由操作基础设施 |

Bioinfoflow 主要面向独立研究者、生信工程师、工作流开发者，以及使用工作站、
实验室服务器或 SSH 计算资源的小型技术团队。

## 现在如何安装

在首个 Release 发布前，请先从源码启动。你需要：

- macOS 或 Linux
- Docker Engine 或 Docker Desktop，并支持 Docker Compose
- `amd64` 或 `arm64` 机器

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
cp .env.example .env

# 启动前修改初始管理员邮箱和密码：
# AUTH_BOOTSTRAP_OWNER_EMAIL、AUTH_BOOTSTRAP_OWNER_PASSWORD
${EDITOR:-vi} .env

docker compose up -d --build
```

只在本机使用时，`BETTER_AUTH_SECRET` 可以留空，Bioinfoflow 会自动生成并保存。
如果要让其他人访问，或部署到远程服务器，请用 `openssl rand -base64 32` 生成一个
固定密钥。源码版 Compose 默认会把前后端端口暴露到主机网络接口，因此请先修改
初始管理员账号，并且只在可信的机器和网络里运行。

启动后打开 <http://localhost:3000>，使用刚才设置的管理员账号登录，然后进入
Agent 页面。

### 一行安装什么时候可以用？

首个带安装器和配套镜像的正式版本发布后，可以直接运行：

```bash
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh
```

**目前 GitHub 上还没有这样的 Release，所以上面的命令现在会下载失败。** 在首个版本
发布并完成安装测试前，请使用上面的源码安装。届时安装器会把数据放在
`~/.bioinfoflow/data`，只监听 `127.0.0.1`，并在启动后直接打开 Agent 页面。
更新、卸载、指定版本和检查脚本等用法见 [Docker 与安装器指南](docs/getting-started/docker.md)。

## 三步跑完第一个演示

首次启动时，Bioinfoflow 会自动准备好一个 `Bioinfoflow Demo` 项目，其中已经有：

- 已注册的 WDL 工作流
- 一份样本表
- 两个很小的 FASTQ 文件
- 可以直接点击的 Agent 快捷指令

你只需要：

1. 在 Agent 输入框里点击**连接模型**，填入模型服务商的 API Key。
2. 点击**检查并运行演示工作流**。
3. 查看 Agent 给出的计划，确认后提交运行。

Agent 会先检查这些文件，再通过 Bioinfoflow 的内置工具准备任务。真正提交任务前，
它会停下来等你确认；任务开始后，它还能继续查看日志、DAG 和输出结果。

OpenAI、Anthropic 和 DeepSeek 可以直接从 Agent 输入框连接。Kimi、Kimi China、
Gemini、OpenRouter、Ollama、vLLM 以及其他兼容接口，可以在
**设置 → AI 服务商**中配置。

## Agent 不是旁边多出来的聊天框

它和 Bioinfoflow 共用同一套项目、工作流注册信息、文件、运行历史、调度状态、
镜像、技能和远程连接。Agent 看到的是项目里的真实状态，调用的也是 Bioinfoflow
自己的工具；需要提交或取消任务时，仍会先征求你的确认。

```text
你提出分析需求
      ↓
Agent 查看项目文件、工作流、输入和历史运行
      ↓
说明计划并准备参数
      ↓
在当前项目和权限范围内调用 Bioinfoflow 工具
      ↓
遇到提交、取消等关键操作时，请求你的批准
      ↓
继续跟踪事件、日志、DAG 和输出
      ↓
解释结果，或定位失败原因
```

查看文件、整理信息等只读操作可以直接进行；提交或取消任务等会产生实际影响的操作，
仍然受权限策略和审批机制约束。对话、工具调用、运行事件和产物都会留有记录；
只有经过你确认的内容才会写入长期记忆。

## 一个项目，把一次分析需要的上下文放在一起

### 数据放在哪里，由你决定

项目可以使用 Bioinfoflow 管理的存储，也可以直接使用已有的本地目录，或者通过 SSH
连接远程计算资源。无论数据放在哪里，文件、工作流、对话、运行历史和结果都收在
同一个项目下，不会散落到彼此无关的页面和目录里。

### 一次运行，之后仍然看得懂

工作流注册一次后，可以从 Web 界面、`bif` CLI 或 Agent 发起。持久化调度器负责
并发、资源、重试、超时、清理和服务重启后的恢复；每次运行的输入、事件、DAG、
日志、审计记录和结果会保存在一起。

Nextflow 与 WDL/MiniWDL 使用同一套项目和运行模型。切换执行引擎时，项目、
运行记录和结果仍然可以沿用。

### 本地掌控，也能按需连接远程资源

Bioinfoflow 运行在你管理的基础设施上。你可以在浏览器终端中操作，也可以用
`bif` CLI 编写脚本，或通过 SSH 连接远程计算资源。平台不会因此变成托管式数据服务；
远程命令仍然受实际使用的 SSH 身份、选中的连接和 Agent 权限策略限制。

## 使用前需要了解的安全边界

- 本机一行安装模式只监听 `127.0.0.1`，不需要注册 Bioinfoflow 云端账号，也不用
  单独安装数据库。
- 研究数据不必离开你控制的基础设施。如果使用云端模型，发送给模型的提示词和上下文
  仍然受对应服务商的数据政策约束。
- 不使用 Agent 时，不需要配置任何模型；使用 Agent 时，需要连接一个云端模型或本地
  兼容模型。
- 执行工作流时，后端会挂载 Docker socket，因此具备主机级的容器控制能力。请只在
  可信机器和可信网络中运行。
- 公网、远程或团队部署仍然需要认证、稳定密钥、TLS、可信来源、备份和常规安全加固。
  本机一行安装模式不会替你完成这些生产环境配置。

如果准备让其他用户访问 Bioinfoflow，请先阅读[安全说明](docs/security.md)、
[存储模型](docs/concepts/storage.md)和[运维手册](docs/operations/runbook.md)。

## 其他运行方式

### 自定义源码部署

如果你需要本地开发、带登录的个人或团队环境、自定义访问地址，或者修改前端构建配置，
请使用源码部署。团队或远程部署还需要设置稳定的 `BIOINFOFLOW_CREDENTIAL_KEY`，
配置实际访问地址和可信来源，启用 TLS，并在开放端口前阅读安全说明。

预构建镜像、自定义数据目录、GPU 和其他部署方式见
[Docker 指南](docs/getting-started/docker.md)；配置优先级与故障排查见
[运行手册](RUNBOOK.md)。

### 命令行

`bif` 是 Bioinfoflow 后端的命令行客户端，需要先启动后端服务：

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

使用 `--base-url` 或 `BIOFLOW_API_URL` 可以连接其他后端。完整命令见
[CLI 参考](docs/reference/cli.md)。

## 本地开发

```bash
# 启动后端
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000

# 在另一个终端启动前端
cd frontend
bun install
bun run dev
```

后端会在启动时加载环境配置，仓库根目录的 `.env` 是默认配置源，`backend/.env`
可用于本机覆盖。修改后需要重启后端；如果改了 `NEXT_PUBLIC_*` 配置，还要重启或
重新构建前端，因为这些值会写进前端产物。

- 后端检查：`uv run pytest && uv run ruff check .`
- 前端检查：`bun run lint && bun run test`

## 文档

- [文档首页](docs/README.md)
- [Docker 与安装器指南](docs/getting-started/docker.md)
- [运行手册](RUNBOOK.md)
- [架构说明](docs/architecture.md)
- [存储与数据布局](docs/concepts/storage.md)
- [远程连接](docs/guides/remote-connections.md)
- [nf-core/rnaseq 示例](demo/nfcore-rnaseq/README.md)

## 开源协议

Bioinfoflow 采用 [MIT License](LICENSE)。
