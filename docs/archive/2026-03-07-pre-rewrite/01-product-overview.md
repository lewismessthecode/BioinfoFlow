# Bioinfoflow Product Overview

**Version:** 0.1  
**Status:** MVP  
**Type:** Local-First Agentic Bioinformatics Platform

---

## 1. Vision & Problem Statement

### Vision
**"Manus for Bioinformatics."**

Bioinfoflow is an intelligent, local-first agentic platform that abstracts away the complexity of bioinformatics engineering (pipelines, configs, resource management) so scientists can focus purely on biological intent.

### Problem Statement
Bioinformatics analysis currently requires a user to be a sysadmin, a programmer, and a biologist simultaneously. Existing GUI tools (like Galaxy) lack flexibility, while command-line tools (Nextflow/WDL) have a steep learning curve.

### Value Proposition
- **Agentic Automation**: Users state their goal ("Analyze these viral sequences"), and Bioinfoflow plans, configures, and executes the pipeline.
- **Local Data Gravity**: Solves the "100GB upload" problem by bringing the compute to the data (Local Docker execution) via smart mounting.
- **Expert Knowledge**: Built-in "Skills" (SOPs) ensure best practices are applied automatically.

### Target Audience
- **Primary**: Wet-lab scientists and junior bioinformaticians who need reproducible analysis without debugging scripts.
- **Secondary**: Senior bioinformaticians who want a "Copilot" to handle routine pipeline executions and error recovery.

---

## 2. Core Features

### A. The Bio-Agent "Brain" (Logic & Knowledge)

The core differentiator is the separation of **Tools** (Capabilities) and **Skills** (Knowledge).

#### Tools (The Hands)
Atomic, executable Python functions that the Agent calls to interact with the system:

| Tool | Description |
|:---|:---|
| `list_docker_images()` | Discover available environments |
| `scan_local_dir(path)` | Recursively find FastQ/BAM files and identify sample naming patterns |
| `search_workflow(query)` | Find appropriate pipelines (Nextflow/WDL; e.g., nf-core or local) |
| `run_shell_cmd(cmd)` | Execute commands in a secure sandbox |
| `read_logs(run_id, lines)` | Smart log retrieval (tailing stderr, filtering Java stack traces) |
| `visualize_result(file_path)` | Generate Plotly charts for frontend rendering |

#### Skills (The Knowledge)
Static Markdown files containing expert Standard Operating Procedures (SOPs). The Agent retrieves and reads these to make decisions:

| Skill | Description |
|:---|:---|
| `skill-ngs-best-practices.md` | "For WGS, use hg38. If file > 50GB, split fastq..." |
| `skill-error-recovery.md` | "If Exit Code 137 (OOM), retry with double memory. If Exit Code 1, check input file paths." |
| `skill-config-generation.md` | Rules for generating valid `nextflow.config` and `samplesheet.csv` |
| `skill-viral-analysis.md` | Pipeline-specific defaults for viral analysis |

### B. Predefined Resource Library

#### Pipeline Pool
Pre-registered, production-ready pipelines that users can run immediately:
- **Coronavirus Analysis** (MVP Demo): Based on `nf-core/viralrecon`, supports SARS-CoV-2 / viral genome analysis (~30kb, fast demo)
- **Local WDL Templates** (MVP): Users can upload `.wdl` files and run them locally
- **Global Workflow Registry**: Uploaded workflows are stored in a shared registry path for reuse across projects

#### Docker Image Registry
Curated, versioned container images for common bioinformatics tools:

| Image | Tools | Base |
|:---|:---|:---|
| `bioinfoflow/bwa` | BWA-MEM2 | Ubuntu 22.04 |
| `bioinfoflow/gatk` | GATK 4.x, Picard | adoptopenjdk |
| `bioinfoflow/samtools` | samtools, bcftools, htslib | Alpine |
| `bioinfoflow/multiqc` | MultiQC, FastQC | python:3.11-slim |

### C. The Engine "Body" (Execution)
- **Multi-Engine (MVP)**: Supports **Nextflow** and **WDL (MiniWDL)** with a shared run interface
- **Docker as Sandbox**: MVP uses Docker containers as the isolated execution sandbox
- **Smart Mounting**: Automatic mapping of user local directories to Docker volumes
- **Extensibility Interface**: Abstract `ExecutionBackend` interface for future K8s/Singularity/Cloud support

### D. Task Lifecycle Management

| Action | Description | MVP Status |
|:---|:---|:---|
| **Submit** | Start a new pipeline run | ✅ |
| **Cancel** | Terminate running pipeline | ✅ |
| **Resume** | Continue from last checkpoint (`-resume`) | ✅ |
| **Pause** | Suspend execution | ❌ (future) |
| **Retry** | Re-run failed tasks with modified config | ✅ (via Self-Healing) |
| **Timeout** | Auto-cancel if exceeds time limit | ❌ (future) |

### E. Self-Healing System
The Agent proactively monitors the `trace` file and `.nextflow.log`:
- **Auto-Retry**: If a job fails with a known error (defined in Skills), the Agent modifies the config and resumes the pipeline automatically
- **User Notification**: Critical failures are reported to the user with a simplified explanation

---

## 3. Success Metrics (KPIs)

| Metric | Definition | MVP Goal |
|:---|:---|:---|
| **Time-to-Result (TTR)** | Total time from intent to final report | < 50% of manual CLI setup |
| **Intervention Rate** | Avg. number of times user must help the agent per run | < 1 |
| **Self-Healing Rate** | % of technical errors (OOM, Network) fixed by Agent | > 80% |
| **User Satisfaction** | "Did the agent understand your biological intent?" | 4.5/5 |

---

## 4. Technical Stack

| Component | Technology |
|:---|:---|
| **Backend** | Python 3.12+ (Managed by `uv`), FastAPI |
| **Agent Orchestration** | LangGraph (for stateful cyclic flows) |
| **Database** | SQLite (MVP); PostgreSQL + pgvector (future) |
| **Frontend** | Next.js 14, Shadcn UI, React Flow, Tailwind CSS |
| **Runtime** | Docker Engine (User must have Docker installed) |
| **Workflow Engines** | Nextflow + MiniWDL (WDL) |

---

## 5. Feature Roadmap

### Priority Definitions

| Priority | Label | Description |
|:---|:---|:---|
| P0 | 🔴 MVP必须 | 没有这个功能产品无法运行 |
| P1 | 🟠 MVP推荐 | 显著提升MVP体验，建议包含 |
| P2 | 🟡 V1.0 | 第一个正式版本需要 |
| P3 | 🟢 后续版本 | 未来迭代考虑 |

### MVP Feature Summary (P0)

| 模块 | 必须功能 |
|:---|:---|
| **引擎** | Nextflow + WDL (MiniWDL), Docker运行, 本地机器 |
| **流程** | DAG可视化(只读), 提交/取消/Resume |
| **资源** | 本地目录挂载, 文件浏览器 |
| **Agent** | 意图理解, 任务规划, Tool Calling |
| **Tools** | list_docker_images, scan_local_dir, search_workflow, read_logs, run_shell_cmd, visualize_result |
| **Skills** | ngs-best-practices, error-recovery, config-generation, viral-analysis |
| **UI** | 对话流, Artifacts卡片, DAG面板, Workspace |
| **后端** | FastAPI, SSE, SQLite (MVP) |

### Version Roadmap

**v0.1 MVP (当前)**
- 🔴 P0 全部功能
- 核心Bioinfo-Agent + 本地Docker执行
- nf-core/viralrecon 病毒分析流程演示
- 本地 WDL 上传与执行

**v0.2**
- 🟠 P1 全部功能
- Predefined流程库 & Docker镜像库
- Thinking Block, Monitor仪表盘

**v0.3 (提议)**
- 🟠 P1 体验强化
- **模型接入与计费**：支持 BYOK（用户自带 API Key）与订阅制（例如 $20/月）两种模式
- Provider 统一入口（OpenAI 兼容协议 + Gemini 原生）

**v1.0**
- 🟡 P2 全部功能
- 任务暂停/超时, 参数编辑
- 云运行接口 (AWS Batch)

**v2.0+**
- 🟢 P3 全部功能
- K8s/Singularity
- 多Agent协作

---

## 6. Feature Pool (Detailed)

### 6.1 Core Engine

#### Workflow Engine Support
| ID | Feature | Priority |
|:---|:---|:---|
| E-001 | Nextflow 流程解析与执行 | 🔴 P0 |
| E-002 | MiniWDL/WDL 流程解析与执行 | 🔴 P0 |
| E-003 | Snakemake 支持 | 🟢 P3 |
| E-004 | 通用 DAG 抽象层 | 🟡 P2 |

#### Execution Environment
| ID | Feature | Priority |
|:---|:---|:---|
| E-010 | Docker 容器执行 | 🔴 P0 |
| E-011 | Singularity 支持 | 🟢 P3 |
| E-012 | Kubernetes 支持 | 🟢 P3 |
| E-013 | 本地进程执行 (无容器) | 🟡 P2 |

#### Platforms
| ID | Feature | Priority |
|:---|:---|:---|
| E-020 | 本地机器运行 | 🔴 P0 |
| E-021 | AWS Batch 云运行 | 🟡 P2 |
| E-022 | Google Cloud Life Sciences | 🟢 P3 |
| E-024 | HPC/Slurm 集群运行 | 🟢 P3 |

### 6.2 Pipeline Management

| ID | Feature | Priority |
|:---|:---|:---|
| P-001 | 流程 DAG 可视化 (只读) | 🔴 P0 |
| P-002 | 流程 DAG 拖拽编辑 | 🟢 P3 |
| P-004 | 流程导入 (从GitHub/Dockstore) | 🟠 P1 |
| P-020 | 提交/启动流程 | 🔴 P0 |
| P-022 | 恢复流程 (-resume) | 🔴 P0 |
| P-023 | 取消/终止流程 | 🔴 P0 |
| P-024 | 失败自动重试 | 🟠 P1 |

### 6.3 Resource Management

| ID | Feature | Priority |
|:---|:---|:---|
| R-001 | 内置 BWA 镜像 | 🟠 P1 |
| R-002 | 内置 GATK 镜像 | 🟠 P1 |
| R-005 | 镜像浏览器/选择器 | 🟠 P1 |
| R-010 | 本地目录挂载 (Smart Mount) | 🔴 P0 |
| R-011 | 拖拽上传小文件 (<1GB) | 🟠 P1 |
| R-014 | 文件浏览器 | 🔴 P0 |

### 6.4 Agent Capabilities

| ID | Feature | Priority |
|:---|:---|:---|
| A-001 | 自然语言理解分析意图 | 🔴 P0 |
| A-002 | 规划与分解任务 | 🔴 P0 |
| A-003 | Tool Calling 框架 | 🔴 P0 |
| A-004 | 多Agent协作编排 | 🟢 P3 |

### 6.5 Frontend UI

| ID | Feature | Priority |
|:---|:---|:---|
| U-001 | 左侧栏: Projects列表 | 🔴 P0 |
| U-003 | 中央: 对话流 (Chat Stream) | 🔴 P0 |
| U-004 | 右侧: Workspace 文件树 | 🔴 P0 |
| U-005 | 右侧: DAG 面板 | 🔴 P0 |
| U-006 | 右侧: Monitor 仪表盘 | 🟠 P1 |
| U-010 | Thinking Block 折叠块 | 🟠 P1 |
| U-011 | Artifacts 卡片系统 | 🔴 P0 |
| U-015 | DAG节点点击查看日志 | 🔴 P0 |
