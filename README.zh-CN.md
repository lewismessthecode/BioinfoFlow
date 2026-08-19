<div align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />

  # Bioinfoflow

  **用自然语言，跑生物信息分析流程。**

  一个让 Agent 真正参与分析工作的本地工作空间。

  说清楚你要完成什么。Agent 会查看项目文件、准备输入、运行 Nextflow
  或 WDL、跟踪日志，并把结果讲明白。数据和运行环境始终由你掌握。

  <p>
    <a href="https://discord.gg/bBZB8bFnHB">Discord 社区</a> ·
    <a href="docs/README.md">文档</a> ·
    <a href="https://bioinfoflow.com">官网</a> ·
    <a href="LICENSE">MIT 许可证</a>
  </p>

  <p><a href="README.md">English</a> · <b>简体中文</b></p>
</div>

## 先跑起来

准备一台安装了 Docker Engine 或 Docker Desktop 的 macOS 或 Linux 电脑。

```bash
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh
```

打开 [localhost:3000](http://localhost:3000)，连接一个模型，然后运行演示流程。

如果要参与开发，或者需要自定义部署方式：

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
docker compose up -d --build
```

安装更新、认证、远程部署、GPU 和语音输入等说明，见
[Docker 与安装器指南](docs/getting-started/docker.md)。

![Bioinfoflow Agent 页面](assets/agent-page-macos.png)

_Agent 页面把对话、项目工作区、执行目标和操作确认放在了一起。_

## 每个页面负责什么

| 页面 | 主要用途 |
| --- | --- |
| **工作区** | 管理项目、文件、对话和一项分析所需的上下文。 |
| **总览** | 查看系统是否准备就绪、Docker 与 GPU 状态、调度情况和最近运行记录。 |
| **Agent** | 用自然语言提出任务；检查文件、准备参数、调用工具，并在确认后执行关键操作。 |
| **工作流** | 注册 Nextflow 或 WDL 流程，管理版本，将流程绑定到项目并启动运行。 |
| **运行** | 查看排队状态、日志、DAG、输出、重试、恢复、取消、清理和审计记录。 |
| **镜像** | 查看和管理工作流镜像，从仓库拉取、上传 tar 包，或在允许时删除镜像。 |
| **连接** | 保存 SSH 主机，测试连接、运行探针、打开远程终端，也可以通过单跳跳板机连接，并把选定的远程主机交给 Agent 使用。 |
| **调度器** | 查看运行队列、活动任务、资源情况和并发度。 |
| **设置** | 管理账户、外观、Agent 权限、AI 服务、容器镜像仓库和团队成员。 |

Bioinfoflow 把项目、流程、运行、日志和结果放在同一个上下文里。数据可以放在
本机、外部项目目录，或你明确选定的 SSH 主机上。远程连接适合检查远程环境和打开
交互式终端；流程运行仍由 Bioinfoflow 的调度器负责。

## GPU 分析流程

仓库里附带了 NVIDIA Parabricks 的 WGS 示例，适用于满足要求的 GPU 环境。像
RTX 4080 SUPER 这样的显卡可以用来在本机运行 GPU 流程；最终能否运行，还取决于
具体流程、NVIDIA 驱动、Docker 的 GPU 运行时和可用显存。

详见 [Parabricks WGS 流程说明](docs/workflows/parabricks-wgs.md)。

## 使用前需要知道的边界

- 本机安装版只监听回环地址，并使用开发认证，适合可信的单用户环境。
- 为了管理镜像和运行流程，Bioinfoflow 会挂载 Docker socket；这意味着后端拥有主机级的 Docker 控制能力。
- 工作流容器必须和主机、后端看到同一个绝对路径下的 `BIOINFOFLOW_HOME`。
- SSH 命令使用选定的远程账户和服务器权限。远程项目根目录只是工作目录，不是安全沙箱。

## 常用入口

- [文档首页](docs/README.md)
- [SSH 远程连接](docs/guides/remote-connections.md)
- [存储与数据目录](docs/concepts/storage.md)
- [架构说明](docs/architecture.md)
- [CLI 参考](docs/reference/cli.md)
- [运行手册](RUNBOOK.md)

## 开发

仓库约定和验证命令见 [AGENTS.md](AGENTS.md)。
直接从源码启动后端时，请先在 `backend/` 目录运行
`npm ci --prefix sandbox_worker`，安装 Agent 本地沙盒 worker 所需的依赖。

## 开源协议

Bioinfoflow 采用 [MIT 许可证](LICENSE)。
