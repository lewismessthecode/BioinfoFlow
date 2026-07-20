<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">Bioinfoflow</h1>

<p align="center">
  <strong>一个让 Agent 真正参与生物信息工作流的本地工作空间。</strong>
</p>

<p align="center">
  不必把零散上下文复制进聊天框。Agent 可以直接检查项目文件、准备输入、
  运行 Nextflow 或 WDL、跟踪日志与 DAG，并在你掌握的基础设施上解释结果。
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/discord-加入-5865F2?logo=discord&logoColor=white" alt="加入 Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/文档-阅读-3b82f6" alt="阅读文档" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/网站-访问-111827" alt="访问网站" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/许可证-MIT-22c55e" alt="MIT License" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow Agent 检查工作流、提交运行并跟踪 DAG" width="100%" />
</p>

## Bioinfoflow 适合你吗？

如果工作流命令本身并不难，真正麻烦的是让输入、容器、参数、日志、工作目录、
结果以及“这次分析到底发生了什么”始终连在一起，Bioinfoflow 会比较有用。

| 比较适合你，如果你…… | 可能不需要，如果你…… |
| --- | --- |
| 在自己的计算资源上运行或开发生信工作流 | 已经习惯直接使用工作流引擎和文件目录管理一切 |
| 希望终端关闭后，失败的运行仍然可以被理解和追溯 | 想要完全托管的数据分析服务 |
| 想统一查看项目文件、输入、运行、DAG、日志和结果 | 需要开箱即用、零运维的多租户平台 |
| 希望 Agent 基于真实状态工作，并在重要操作前请求审批 | 希望 Agent 不经审核地自由修改基础设施 |

Bioinfoflow 首先面向独立研究者、生信工程师、工作流开发者，以及使用工作站、
实验室服务器或明确连接的远程资源的小型技术团队。

## 安装并完成第一次分析

环境要求：macOS 或 Linux、支持 Compose 的 Docker Engine 或 Docker Desktop，
以及 `amd64` 或 `arm64` 机器。

在首个带安装器与容器镜像的 tag 发布前，请先克隆仓库并从源码构建当前版本：

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
cp .env.example .env

# 启动前编辑 .env，至少替换以下配置：
# AUTH_BOOTSTRAP_OWNER_EMAIL、AUTH_BOOTSTRAP_OWNER_PASSWORD、BETTER_AUTH_SECRET
${EDITOR:-vi} .env

docker compose up -d --build
```

可以运行 `openssl rand -base64 32` 生成 `BETTER_AUTH_SECRET`，再把结果填入
`.env`。源码 Compose 默认会把前后端端口发布到主机网络接口，因此必须在启动前
修改初始所有者账号、密码和密钥，并且只在可信机器与网络中运行。

打开 <http://localhost:3000>，使用刚刚配置的所有者账号登录，然后进入 Agent
页面。

第一次有效运行只需要三步：

1. 在 Agent 输入框（composer）中点击**连接模型**，粘贴模型服务商的 API Key。
2. 点击**检查并运行演示工作流**。
3. 查看 Agent 的计划，并批准工作流提交。

新工作空间包含 `Bioinfoflow Demo` 项目、注册好的 WDL 工作流、样本表和
两个很小的 FASTQ 输入。Agent 会检查这些真实文件，通过 Bioinfoflow 的正常
工具准备运行，在提交前停下来等待审批；审批后，它可以检查或跟踪日志与结果。

模型配置以界面为主。OpenAI、Anthropic 和 DeepSeek 可以直接从 Agent 输入框
快速连接；Kimi、Kimi China、Gemini、OpenRouter、Ollama、vLLM
以及其他兼容接口仍可在**设置 → AI 服务商**中配置。

<details>
<summary>本机一键安装器（首个 tag 发布后可用）</summary>

首个包含本次改动的 tag 会发布 `install.sh` 和本机安装器所用的带版本容器镜像。
该 release 发布后，一键安装命令将是：

```bash
# 从最新 tag 安装
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh

# 或者先下载检查，再执行
curl -fLO https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh
less install.sh
sh install.sh

# 更新与卸载
~/.bioinfoflow/install/install.sh --update
~/.bioinfoflow/install/install.sh --uninstall  # 保留数据
~/.bioinfoflow/install/install.sh --purge      # 删除托管数据
```

安装器还支持 `--dry-run`、`--version <tag>` 和 `--no-open`。
它会拉取带版本的镜像，把数据保存在 `~/.bioinfoflow/data`，只监听
`127.0.0.1`，等待服务健康后直接打开 Agent 页面，不显示 Bioinfoflow 登录页。
在 tag 发布前，请使用上面的源码安装方式。

</details>

## Agent 通过平台开展工作

Agent 不是放在工作流面板旁边的聊天框。它与 Bioinfoflow 其他部分使用同一套
项目、工作流注册、运行历史、调度状态、文件、镜像、技能和选中的远程连接。

```text
你的分析需求
      ↓
检查项目文件、工作流、输入和历史运行
      ↓
解释计划并准备配置
      ↓
在选定项目和权限范围内调用 Bioinfoflow 工具
      ↓
在重要操作前停下来请求审批
      ↓
检查或跟踪事件、日志、DAG 状态和输出
      ↓
解释结果，或者诊断失败原因
```

查看与整理工作可以直接进行。提交或取消运行等操作仍受到当前权限策略和显式
审批约束。Agent 会话、工具动作、事件、产物和被接受的记忆都可以检查，而不是
消失在一段没有结构的聊天记录里。

## 哪些内容被放到了一起

### 无论数据位于哪里，项目都是稳定边界

项目可以使用 Bioinfoflow 管理的存储、已有本地目录，也可以连接 SSH 远程项目。
文件、工作流绑定、对话、运行历史和输出始终附着在同一个项目边界上。

### 一次运行可以被重新理解

工作流注册一次后，可以从 Web 界面、`bif` CLI 或 Agent 发起。持久化调度器
负责并发、资源、重试、超时、清理和重启恢复；输入、事件、DAG、日志、审计记录
和收集到的结果则保存在同一个运行上下文中。

Nextflow 与 WDL/MiniWDL 位于统一的项目和运行模型之后。更换执行引擎时，
不需要重新组织外围的工作空间。

### 本地掌控，按明确边界连接远程资源

平台运行在你掌握的基础设施上。浏览器终端、`bif` CLI 和保存的 SSH 连接覆盖
交互式与脚本化操作，但不会把 Bioinfoflow 变成托管式数据服务。远程命令仍然
受到所选连接、SSH 身份和 Agent 权限策略的共同约束。

## 需要了解的信任边界

- 本机安装器只监听 `127.0.0.1`，不需要托管的 Bioinfoflow 账号，也不需要
  单独安装数据库。
- 研究数据不必离开你掌握的基础设施。如果使用托管模型，发送给该模型的提示词
  和上下文适用对应服务商的数据政策。
- 手动使用工作流不要求配置模型；使用 Agent 时需要一个可用的托管模型或本地
  兼容模型。
- 执行工作流时，后端会挂载 Docker socket，因此拥有主机级容器控制能力。只应
  在你信任的机器和网络中使用。
- 公网、远程或团队部署需要认证、稳定密钥、TLS、可信来源、备份和常规加固。
  本机安装器不会尝试代替你配置这些环境。

将 Bioinfoflow 暴露给其他用户前，请阅读[安全说明](docs/security.md)、
[存储模型](docs/concepts/storage.md)和[运维手册](docs/operations/runbook.md)。

## 其他运行方式

### 配置源码部署

上面的源码安装方式也适用于本地开发、需要认证的个人或团队部署、自定义公网地址，
以及修改前端构建配置。用于团队或远程环境时，还要设置稳定的
`BIOINFOFLOW_CREDENTIAL_KEY`，配置真实的浏览器地址与可信来源，启用 TLS，并在
开放端口前阅读安全说明。登录后可以配置 AI 服务商。

发布镜像、自定义数据目录、GPU 和部署方式见 [Docker 指南](docs/getting-started/docker.md)；
配置优先级与故障排查见[运行手册](RUNBOOK.md)。

### 命令行

`bif` 是运行中 Bioinfoflow 后端的 HTTP 客户端：

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

可以使用 `--base-url` 或 `BIOFLOW_API_URL` 选择其他后端。完整命令见
[CLI 参考](docs/reference/cli.md)。

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

后端检查使用 `uv run pytest && uv run ruff check .`；前端检查使用
`bun run lint && bun run test`。

## 文档

- [文档首页](docs/README.md)
- [Docker 与安装器指南](docs/getting-started/docker.md)
- [运行手册](RUNBOOK.md)
- [架构说明](docs/architecture.md)
- [存储与数据布局](docs/concepts/storage.md)
- [远程连接](docs/guides/remote-connections.md)
- [nf-core/rnaseq 示例](demo/nfcore-rnaseq/README.md)

## 许可证

Bioinfoflow 以 [MIT License](LICENSE) 发布。
