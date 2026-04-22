# Bioinfoflow Frontend Design [CANONICAL]

**Version:** 0.3
**Status:** MVP
**Last Updated:** 2026-03-07

---

## 1. Design Philosophy

**"Cursor meets Manus for Bioinformatics"**

A modern, intelligent interface that feels like a conversation with an expert colleague. Prioritize clarity over information density, and progressive disclosure over overwhelming dashboards.

### Anti-AI-Slop Principles

| Do | Don't |
|---|---|
| Specific, concrete language | Vague, generic marketing copy |
| Real or clearly labeled demo data | Fake institution names, anonymous quotes |
| Purposeful animations | Auto-cycling carousels, bouncy effects |
| Function-first design | Decoration without purpose |
| Custom, contextual touches | Template-driven patterns |

### Visual Direction: Modern SaaS

- **Typography**: Clean, generous whitespace, proper hierarchy
- **Color**: Monochromatic base with single accent for CTAs
- **Motion**: Subtle, purposeful, respects reduced-motion preferences
- **Depth**: Subtle shadows over gradients
- **Spacing**: Consistent rhythm, breathing room

### Copy Guidelines

- **Headlines**: Be specific, not generic. Lead with the benefit. Avoid AI cliches ("feels like", "seamless", "unlock").
- **Body Text**: Short sentences. Active voice. Concrete examples over abstractions.
- **CTAs**: Action-oriented. Clear outcome. Single primary CTA per section.

### Success Criteria

- All placeholder content replaced with authentic or clearly labeled demo content
- Animations refined to be purposeful, not decorative
- Consistent visual language across landing, auth, and app experiences
- Mobile responsive at all major breakpoints
- Lighthouse performance score > 90

---

## 2. Technology Stack

| Layer | Technology |
|:---|:---|
| Framework | Next.js 14 (App Router) |
| UI Library | Shadcn UI |
| Styling | Tailwind CSS |
| DAG Visualization | React Flow |
| Charts | Shadcn Charts (Recharts) |
| State Management | Zustand |
| Real-time | SSE (EventSource) |
| Icons | Lucide React |

---

## 3. Navigation Architecture

### 3.1 Top Navbar

借鉴 Mobbin 的简洁 Navbar 风格：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🧬 Bioinfoflow                                                          │
│                                                                         │
│   [Agent]   [Workflows]   [Runs]   [Images]              🔔  ☀️  👤     │
│     ▔▔▔▔▔                                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

| Tab | 说明 | 路由 |
|:---|:---|:---|
| **Agent** | AI 对话界面 | `/agent` |
| **Workflows** | 已注册的流程模板库 | `/workflows` |
| **Runs** | 任务执行历史/作业管理 | `/runs` |
| **Images** | Docker 镜像管理 | `/images` |

**右侧图标：**
- 🔔 通知中心
- ☀️/🌙 主题切换
- 👤 用户头像（点击展开菜单）

### 3.2 Left Sidebar

侧边栏分为**上下两部分**：

```
┌─────────────────────┐
│ 🧬 Bioinfoflow    [<]   │  ← 折叠按钮
├─────────────────────┤
│                     │
│ Projects            │  ← 上半部分：项目列表
│ ─────────────────   │
│ 🔍 Search...        │
│                     │
│ 📂 COVID Analysis   │  ← 当前选中
│ 📁 RNA-Seq Batch 1  │
│ 📁 Metagenomics Q4  │
│                     │
│ + New Project       │
│                     │
│ Conversations       │  ← 当前项目的对话列表
│ ─────────────────   │
│ 🗨️ Demo Run         │
│ 🗨️ Variant QC       │
│ + New Conversation  │
│                     │
├─────────────────────┤  ← 分隔线
│ ⚙️ Settings         │  ← 下半部分：系统功能
│ ❓ Get Help         │
│ 🔍 Search           │
│ 🌙 Dark Mode    [○] │  ← Toggle
├─────────────────────┤
│ 🧑‍💻 shadcn         ⋮│  ← 用户信息
│ m@example.com       │
└─────────────────────┘
```

---

## 4. Layout Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Header / Navbar                              │
│  [Logo] Bioinfoflow                              [Settings] [User]   │
├──────────┬────────────────────────────┬─────────────────────────────┤
│          │                            │                             │
│ Sidebar  │      Chat Stream           │      Live Deck              │
│  (240px) │      (Flex: 1)             │      (420px)                │
│          │                            │                             │
│ Projects │  ┌─────────────────────┐   │  ┌─────────────────────┐    │
│ ────────  │  │ Agent Message      │   │  │ [Workspace][DAG][📊] │    │
│ > Project1│  │ <Thinking>...</>   │   │  ├─────────────────────┤    │
│   Project2│  │ Artifact Card      │   │  │                     │    │
│   Project3│  └─────────────────────┘   │  │   Active Tab View   │    │
│          │                            │  │                     │    │
│ ────────  │  ┌─────────────────────┐   │  │                     │    │
│ Settings │  │ User Message        │   │  └─────────────────────┘    │
│          │  └─────────────────────┘   │                             │
│          │                            │                             │
│          │  ┌─────────────────────┐   │                             │
│          │  │ 💬 Input Box        │   │                             │
│          │  └─────────────────────┘   │                             │
└──────────┴────────────────────────────┴─────────────────────────────┘
```

### Responsive Behavior

| Breakpoint | Layout |
|:---|:---|
| Desktop (≥1280px) | Full 3-column layout |
| Laptop (1024-1279px) | Sidebar collapsible, 2-column |
| Tablet (768-1023px) | Sidebar hidden (hamburger), 1-column |
| Mobile (<768px) | Bottom navigation, stacked cards |

---

## 5. Page Specifications

### 5.1 Agent Page

**路由:** `/agent`

现有的 AI 对话界面，包含快速入口：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Navbar: [Agent▔▔▔] [Workflows] [Runs] [Images]            🔔 ☀️ 👤     │
├──────────┬────────────────────────────┬─────────────────────────────────┤
│ Sidebar  │      Chat Stream           │      Live Deck                  │
│          │                            │                                 │
│ Projects │  [💬 Ask Agent]            │  [Files] [Pipeline▔▔] [Monitor] │
│          │           OR               │                                 │
│          │  [📋 Run from Template →]  │       DAG Viewer                │
│          │                            │                                 │
│          │  ┌───────────────────┐     │                                 │
│          │  │ Chat messages...  │     │                                 │
│          │  └───────────────────┘     │                                 │
└──────────┴────────────────────────────┴─────────────────────────────────┘
```

#### Quick Actions 区域

```
┌─────────────────────────────────────────────────────────────────┐
│  🤖 Ask Agent                          📋 Run from Template     │
│  Describe your analysis in             Select a workflow and    │
│  natural language                      configure parameters     │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Workflows Page

**路由:** `/workflows`

流程注册和管理中心，支持卡片/列表视图切换。
> **共享语义：** Workflows 属于全局共享库（跨项目复用），Runs 仍按 Project 隔离显示。

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Navbar: [Agent] [Workflows▔▔▔] [Runs] [Images]            🔔 ☀️ 👤     │
├──────────┬──────────────────────────────────────────────────────────────┤
│          │                                                              │
│ Sidebar  │  Workflows                           [🔍 Search]            │
│          │  Registered pipeline templates                               │
│          │                                                              │
│          │  [ + Register Workflow ]       [≡ List] [▦ Cards▔]          │
│          │                                                              │
│          │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│          │  │ 🧬          │ │ 🧬          │ │ 🧬          │            │
│          │  │ viralrecon  │ │ rnaseq      │ │ sarek       │            │
│          │  │             │ │             │ │             │            │
│          │  │ nf-core     │ │ nf-core     │ │ nf-core     │            │
│          │  │ v2.6.0      │ │ v3.14.0     │ │ v3.4.0      │            │
│          │  │             │ │             │ │             │            │
│          │  │ [Run] [···] │ │ [Run] [···] │ │ [Run] [···] │            │
│          │  └─────────────┘ └─────────────┘ └─────────────┘            │
│          │                                                              │
└──────────┴──────────────────────────────────────────────────────────────┘
```

#### Workflow Card

```
┌───────────────────────────────────┐
│ 🧬                                │  ← 流程图标
│                                   │
│ nf-core/viralrecon               │  ← 流程名称
│ Viral genome analysis pipeline    │  ← 描述
│                                   │
│ 🏷️ nf-core  ⚙️ nextflow  📦 v2.6.0  ⏱️ ~15min │  ← 元信息
│                                   │
│ [▶️ Run]              [···]       │  ← 操作按钮
└───────────────────────────────────┘
```

### 5.3 Runs Page

**路由:** `/runs`

所有流程运行历史，表格形式展示。

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Navbar: [Agent] [Workflows] [Runs▔▔▔] [Images]            🔔 ☀️ 👤     │
├──────────┬──────────────────────────────────────────────────────────────┤
│          │                                                              │
│ Sidebar  │  Runs                                [🔍 Search] [Filter ▼] │
│          │  Pipeline execution history                                  │
│          │                                                              │
│          │  ┌───────────────────────────────────────────────────────┐  │
│          │  │ □  Run ID      Pipeline     Status   Started   ...    │  │
│          │  ├───────────────────────────────────────────────────────┤  │
│          │  │ □  run_a1b2c3  viralrecon   🟢 Done  10:30 AM  ...    │  │
│          │  │ □  run_d4e5f6  rnaseq       🔵 Run   09:15 AM  ...    │  │
│          │  │ □  run_g7h8i9  sarek        🔴 Fail  Yesterday ...    │  │
│          │  │ □  run_j0k1l2  viralrecon   🟢 Done  Yesterday ...    │  │
│          │  └───────────────────────────────────────────────────────┘  │
│          │                                                              │
│          │  Showing 1-10 of 47 runs                    [<] 1 2 3 [>]   │
└──────────┴──────────────────────────────────────────────────────────────┘
```

#### Table Fields

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| **Run ID** | string | 唯一标识，可点击查看详情 |
| **Pipeline** | string | 流程名称 |
| **Status** | enum | 🟢 Completed, 🔵 Running, 🟡 Queued, 🔴 Failed, ⚪ Cancelled |
| **Started** | datetime | 开始时间 |
| **Duration** | duration | 运行时长 |
| **Workspace** | path | 分析目录路径 |
| **Samples** | number | 样本数量 |
| **Actions** | buttons | 操作按钮 |

#### Status Badge Styles

```
🟢 Completed  →  绿色背景 (#10B981)
🔵 Running    →  蓝色背景 (#3B82F6) + 脉冲动画
🟡 Queued     →  黄色背景 (#F59E0B)
🔴 Failed     →  红色背景 (#EF4444)
⚪ Cancelled  →  灰色背景 (#6B7280)
```

#### Run Detail Sheet (Slide-over Panel)

Clicking a run opens a polished detail sheet with the following structure:

```
┌─────────────────────────────────────────────────────────┐
│ run_436a2e                                          [✕] │  ← Sticky header
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ PIPELINE        STATUS                              │ │
│ │ corona-nf       [Running]                           │ │  ← Metadata card
│ │                                                     │ │
│ │ STARTED         DURATION                            │ │
│ │ 2026/1/21       00:05:23                            │ │
│ │ ─────────────────────────────────────────────────── │ │
│ │ WORKSPACE                                           │ │
│ │ /path/to/workspace                                  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ [Pipeline DAG] [Logs] [Output Files]                    │  ← Tabs (grid layout)
│ ┌─────────────────────────────────────────────────────┐ │
│ │                                                     │ │
│ │           Tab content area                          │ │
│ │       (min-h: 280px, max-h: 400px)                  │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ [████ Download Results ████]  [Re-run]  [Delete]        │  ← Action buttons
└─────────────────────────────────────────────────────────┘
```

**Design Details:**

| Element | Styling |
|:---|:---|
| **Header** | Sticky, `border-b`, `px-6 py-4` |
| **Metadata Card** | `rounded-xl`, `bg-secondary/30`, `p-5` |
| **Labels** | `text-xs font-medium uppercase tracking-wider` |
| **Grid Layout** | `grid-cols-2`, `gap-x-8 gap-y-5` |
| **Workspace Row** | Separated by `border-t border-border/50` |
| **Tabs** | `grid grid-cols-3 h-11` |
| **Tab Content** | `min-h-[280px] max-h-[400px] rounded-xl` |
| **Empty States** | Centered with `flex items-center justify-center` |
| **Download Button** | `flex-1 h-11` (primary style) |
| **Delete Button** | `text-destructive hover:bg-destructive/10` |

### 5.4 Images Page

**路由:** `/images`

Docker 镜像库管理，卡片形式展示。
> **共享语义：** Images 属于全局共享库（跨项目复用），Runs 仍按 Project 隔离显示。

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Navbar: [Agent] [Workflows] [Runs] [Images▔▔▔]            🔔 ☀️ 👤     │
├──────────┬──────────────────────────────────────────────────────────────┤
│          │                                                              │
│ Sidebar  │  Images                              [🔍 Search]            │
│          │  Docker container registry                                   │
│          │                                                              │
│          │  [ + Upload Image ]            [≡ List] [▦ Cards▔]          │
│          │                                                              │
│          │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│          │  │ 🐳          │ │ 🐳          │ │ 🐳          │            │
│          │  │ bioinfoflow/│ │ bioinfoflow/│ │ bioinfoflow/│            │
│          │  │ bwa         │ │ gatk        │ │ samtools    │            │
│          │  │             │ │             │ │             │            │
│          │  │ 📦 v2.2.1   │ │ 📦 v4.5.0   │ │ 📦 v1.18    │            │
│          │  │ 💾 1.2 GB   │ │ 💾 2.8 GB   │ │ 💾 500 MB   │            │
│          │  │ ✅ Local    │ │ ☁️ Remote   │ │ ✅ Local    │            │
│          │  │             │ │             │ │             │            │
│          │  │ [Pull] [···]│ │ [Pull] [···]│ │ [Pull] [···]│            │
│          │  └─────────────┘ └─────────────┘ └─────────────┘            │
│          │                                                              │
└──────────┴──────────────────────────────────────────────────────────────┘
```

**状态标识：**
- ✅ Local → 本地已存在
- ☁️ Remote → 需要 Pull
- 🔄 Pulling → 正在下载

---

## 6. Chat Components

### 6.1 Message Types

**User Message**
```
┌─────────────────────────────────────────────────────────┐
│ 👤  I have SARS-CoV-2 samples in /data/covid.          │
│     Please run variant calling.                         │
│                                              12:34 PM   │
└─────────────────────────────────────────────────────────┘
```

**Agent Message with Thinking Block**
```
┌─────────────────────────────────────────────────────────┐
│ 🤖  Let me analyze your request...                      │
│                                                         │
│ ┌─ Thinking ──────────────────────────────────────┐    │
│ │ ▾ Analyzing input files...                      │    │
│ │   Found 3 paired-end samples                    │    │
│ │   Detected FASTQ format (gzipped)               │    │
│ │   Searching for appropriate pipeline...         │    │
│ └─────────────────────────────────────────────────┘    │
│                                                         │
│ I found 3 SARS-CoV-2 samples. I recommend using        │
│ **nf-core/viralrecon** for variant calling.            │
└─────────────────────────────────────────────────────────┘
```
- Thinking block is **collapsible** (collapsed by default after completion)
- Content streams with **typewriter effect**
- Keywords are **syntax-highlighted**

**Artifact Card**
```
┌─────────────────────────────────────────────────────────┐
│ 📄 Artifact: samplesheet.csv                            │
│ ┌─────────────────────────────────────────────────┐    │
│ │ sample,fastq_1,fastq_2                          │    │
│ │ S001,S001_R1.fq.gz,S001_R2.fq.gz               │    │
│ │ S002,S002_R1.fq.gz,S002_R2.fq.gz               │    │
│ │ ... (3 rows)                                    │    │
│ └─────────────────────────────────────────────────┘    │
│ [👁️ Preview] [✏️ Edit] [📋 Copy]                        │
└─────────────────────────────────────────────────────────┘
```

**Plan Card**
```
┌─────────────────────────────────────────────────────────┐
│ 📋 Analysis Plan                                        │
├─────────────────────────────────────────────────────────┤
│ Pipeline      nf-core/viralrecon v2.6.0                │
│ Reference     MN908947.3 (Wuhan-Hu-1)                  │
│ Samples       3 paired-end                              │
│ Resources     4 CPUs, 16GB RAM                          │
├─────────────────────────────────────────────────────────┤
│ 📄 samplesheet.csv        [View]                        │
│ ⚙️ nextflow.config         [View]                        │
├─────────────────────────────────────────────────────────┤
│        [Cancel]              [🚀 Start Analysis]        │
└─────────────────────────────────────────────────────────┘
```

**Status Card**
```
┌─────────────────────────────────────────────────────────┐
│ 🔄 Analysis In Progress                    ⏱️ 02:34     │
├─────────────────────────────────────────────────────────┤
│ ████████████░░░░░░░░  45%  (12/27 tasks)               │
│                                                         │
│ Current: IVAR_CONSENSUS (Sample S002)                   │
├─────────────────────────────────────────────────────────┤
│        [⏸️ Pause]              [⏹️ Cancel]               │
└─────────────────────────────────────────────────────────┘
```

**Completion Card**
```
┌─────────────────────────────────────────────────────────┐
│ ✅ Analysis Complete                       ⏱️ 08:47     │
├─────────────────────────────────────────────────────────┤
│ 📊 MultiQC Report           [Open]                      │
│ 🧬 Lineage: BA.2.86         [Details]                   │
│ 🔬 12 variants detected     [View Table]                │
├─────────────────────────────────────────────────────────┤
│ [📥 Download All Results]                               │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Thinking + Trace (v2)

目标：给用户**清晰可控的过程感**（类似 o1 / Codex / Claude Code 的执行流），但避免暴露模型内部推理细节。

**结构（可折叠）：**
- **Summary**：1-2 条“可解释”高层摘要（非 chain-of-thought）
- **Tool Trace**：每个工具调用一行（名称、状态、耗时、简短输出摘要）
- **Artifacts / Files**：重要结果卡片（可预览/复制）

**行为规范：**
- Tool Trace 默认折叠，出现错误时自动展开。
- 重复调用进行合并（例如 `search_workflows x3`），避免卡片刷屏。
- 空结果必须显示明确空态（例如 “No workflows matched”）。

### 6.3 Demo Quick Actions (One‑Click Run)

**目标：** 任何 Demo 卡片点击后，**一条路径完成“注册 → 运行 → 跳转 Runs”**。

**交互：**
- Demo 卡片双入口：
  - **Run Demo**（一键运行）
  - **Ask Agent**（只发对话）
- 运行前自动检查：
  - workflow 是否已注册（未注册则自动注册）
  - Docker 是否可用（不可用则提示改用 local profile）
- 运行后：
  - 弹出 toast + 跳转到 Runs
  - 在 Runs 中高亮该 run
- 卡片内展示 Demo 数据来源（例如 `demo/workspace`）

### 6.4 Conversation Management

**需求：** 保留历史对话，同时支持“新对话”而不是 /clear 覆盖历史。

**UI 方案：**
- Chat 顶部新增 **New Conversation** 按钮
- 在 Project 下方新增 **Conversation 列表**
- 支持重命名 / 删除 / Pin
- `/clear` 只清空当前对话 UI，不删除历史（历史仍可从列表恢复）

### 6.5 Slash Commands

**输入框支持：** `/` 命令 + 自动补全。

建议命令：
- `/new` 新对话
- `/clear` 清空当前对话 UI
- `/run` 执行当前 Plan
- `/demo` 打开 Demo 列表
- `/publish` 导出对话/结果
- `/help` 显示命令帮助

### 6.6 Agent Debug / Trace Drawer

为开发者与高级用户提供：
- Prompt / Response（可折叠，默认隐藏）
- Tool calls (args/output/time)
- Token / latency / provider
- 仅在 `AGENT_OBSERVABILITY=true` 时显示

---

## 7. Live Deck (Right Panel)

### Tab 1: Workspace (File Browser)

```
┌─────────────────────────────────────────────────────────┐
│ 📁 /data/covid_samples                    [⟳] [↑]      │
├─────────────────────────────────────────────────────────┤
│ 📂 raw/                                                 │
│    📄 S001_R1.fq.gz              1.2 GB                │
│    📄 S001_R2.fq.gz              1.2 GB                │
│    📄 S002_R1.fq.gz              1.1 GB                │
│ 📂 results/                                             │
│    📂 multiqc/                                          │
│    📄 variants.vcf               2.3 MB                │
├─────────────────────────────────────────────────────────┤
│ Selected: S001_R1.fq.gz                                 │
│ [Preview] [Download] [Delete]                           │
└─────────────────────────────────────────────────────────┘
```

### Tab 2: Pipeline DAG

```
┌─────────────────────────────────────────────────────────┐
│ Pipeline: nf-core/viralrecon              [🔍+] [🔍-]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│    ┌──────────┐      ┌──────────┐                      │
│    │ FASTP   │──────▶│ BWA_MEM  │                      │
│    │   ✅    │      │   🔄     │                      │
│    └──────────┘      └────┬─────┘                      │
│                           │                             │
│                      ┌────▼─────┐                      │
│                      │ IVAR    │                      │
│                      │   ⏳    │                      │
│                      └────┬─────┘                      │
│                           │                             │
│    ┌──────────┐      ┌────▼─────┐                      │
│    │ PANGOLIN │◀─────│ MULTIQC  │                      │
│    │   ⬜    │      │   ⬜    │                      │
│    └──────────┘      └──────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Node States:**
| Icon | State | Color |
|:---|:---|:---|
| ⬜ | Pending | Gray (#6B7280) |
| 🔄 | Running | Blue (#3B82F6) with pulse animation |
| ✅ | Success | Green (#10B981) |
| ❌ | Failed | Red (#EF4444) |
| ⏳ | Queued | Yellow (#F59E0B) |

### Tab 3: Monitor

```
┌─────────────────────────────────────────────────────────┐
│ System Resources                         [Live] [1h]    │
├─────────────────────────────────────────────────────────┤
│ CPU Usage                                               │
│ ▂▃▅▆█▇▅▃▂▃▅▇█▇▅▄▃▂▁  78%                               │
│ ────────────────────────────────────────────── 100%     │
├─────────────────────────────────────────────────────────┤
│ Memory                                                  │
│ ████████████░░░░░░░░  12.4 / 16 GB (77%)               │
├─────────────────────────────────────────────────────────┤
│ Active Tasks        4 / 6                               │
│ Completed           12                                  │
│ Failed              0                                   │
│ Queue               8                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Micro-Interactions

### Banner Notifications
```
┌─────────────────────────────────────────────────────────────────────┐
│ 🚀 Analysis Started: nf-core/viralrecon                    [✕]     │
└─────────────────────────────────────────────────────────────────────┘
```
- Slides in from top
- Auto-dismiss after 5s (unless critical)
- Types: Info (blue), Success (green), Warning (amber), Error (red)

### Toast Notifications
```
                                        ┌────────────────────────┐
                                        │ ✅ FASTP completed     │
                                        │    3 samples processed │
                                        └────────────────────────┘
```
- Bottom-right corner
- Stack up to 3 visible
- Auto-dismiss after 3s

### Loading States
| Component | Loading State |
|:---|:---|
| Chat | Pulsing dots "..." |
| File Tree | Skeleton shimmer |
| DAG | Nodes with pulse animation |
| Charts | Skeleton bars |

### Command Palette (Cmd+K)

**目标：** 快速导航 + 动作触发（类似 Linear/Arc）。

**可执行动作：**
- 新建 Project / Conversation
- 快速打开 Workflows / Runs / Images
- 运行 Demo（SARS / E. coli / Yeast）
- 搜索文件、运行、对话

**实现建议：**
- 前端使用 `cmdk` 或 `@radix-ui/react-dialog` + 自定义 list
- 结果分组（Projects / Runs / Workflows / Conversations / Actions）

---

## 9. Landing Page

### Brand & Messaging

**Product One-liner:**
"Bioinfoflow is the local-first, agentic platform that turns biological intent into reproducible pipelines."

**Primary Value Themes:**
1. **Agentic Automation**: "Tell us your biological goal; we handle the pipeline."
2. **Local-First Compute**: "Keep your data where it lives. Run heavy workflows without uploads."
3. **Self-Healing**: "Automatic retries and smarter error recovery."
4. **Reproducibility**: "Structured runs, configs, and audit trails by default."

### Landing Sections

1. **Hero Section** - Headline + CTA with product preview
2. **Trust Bar** - Grayscale logos for social proof
3. **Product Tabs** - Showcase Agent, Workflows, Runs, Images
4. **Bento Grid** - 4-6 key feature cards
5. **How It Works** - 4-step timeline
6. **Deep Quote** - Large typographic testimonial
7. **Results & Outcomes** - KPIs and minimal charts
8. **Security & Privacy** - Local-first emphasis
9. **Final CTA** - Conversion section

### Visual Design System

- **Colors**: Monochrome (Primary: #171717, Muted: #737373, Background: #FFFFFF)
- **Typography**: Inter (headlines), Geist Mono (technical labels)
- **Layout**: 12-column grid, 24px gutters, max-width 1200-1280px
- **Motion**: Minimal, calm (200-600ms), fade-in on scroll
- **Textures**: Subtle dotted grid (2px dot, 16px spacing, 3-5% opacity)

---

## 10. Landing Page Refinements (v0.3)

### 10.1 Scroll Animations

Using **Framer Motion** for scroll-triggered animations across all landing sections.

| Animation Type | Usage | Duration |
|:---|:---|:---|
| **Fade In on Scroll** | All section headers and content blocks | 400-600ms |
| **Slide Up on Scroll** | Cards, feature items, KPIs | 500-700ms |
| **Stagger Children** | Grid items, timeline steps | 100ms delay each |
| **Counter Animation** | KPI numbers (70%, <1, Minutes) | 1500ms |

**Accessibility:** All animations respect `prefers-reduced-motion` media query.

### 10.2 Hero Section Highlight

"Agentic workflows" gets a **marker highlight effect**:

```css
.highlight-marker {
  background-image: linear-gradient(120deg, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.08) 100%);
  background-repeat: no-repeat;
  background-size: 100% 40%;
  background-position: 0 88%;
  transition: background-size 0.3s ease;
}
```

**"real-world biology"** uses `white-space: nowrap` to prevent awkward line-break.

### 10.3 Trust Bar Improvements

| Before | After |
|:---|:---|
| `text-muted-foreground/40` | `text-foreground/60` |
| `text-lg` | `text-xl tracking-tight` |
| `py-8` | `py-12` |
| Basic border | Gradient fade borders |

### 10.4 Component Visual Hierarchy

**Product Tabs:**
- Larger preview window (min-height 300px)
- Subtle shadow on active tab
- Fade transition on tab switch

**Bento Grid:**
- Reduced whitespace in large cards
- Proportional icon and visual sizing
- Subtle hover scale effect (1.02x)

**How It Works:**
- Dashed connector lines between steps
- Chevron arrows at connection points
- Staggered fade-in animation

**Results Section:**
- Larger KPI numbers (text-5xl → text-6xl)
- Animated counter effect on scroll
- Better chart visual polish

---

## 11. Accessibility Requirements

| Category | Requirement |
|:---|:---|
| Keyboard | Full navigation via Tab, Enter, Escape |
| Screen Reader | ARIA labels on all interactive elements |
| Color Contrast | WCAG AA (4.5:1 for text) |
| Motion | `prefers-reduced-motion` support |
| Focus | Visible focus rings on all elements |

---

## 11. Performance Targets

| Metric | Target |
|:---|:---|
| First Contentful Paint | < 1.5s |
| Time to Interactive | < 3s |
| SSE Latency | < 100ms |
| DAG Render (100 nodes) | < 500ms |
| Streaming Text Latency | < 50ms perceived |

---

## 12. MVP Scope

### ✅ In Scope
- Three-column layout
- Chat with Thinking blocks and Artifacts
- DAG visualization (read-only)
- Basic file browser
- Real-time status updates
- Banner and Toast notifications
- Dark mode default + light mode toggle
- Landing page with Attio-inspired design

### ❌ Out of Scope (Future)
- DAG drag-and-drop editing
- Multi-user collaboration
- Mobile responsive layout
- Internationalization (i18n)
- Onboarding wizard
- Full auth flow (passkey + magic link)

---

## 13. API Endpoints (Frontend 需要)

| Method | Endpoint | Description |
|:---|:---|:---|
| GET | `/api/v1/workflows` | 获取流程列表 |
| POST | `/api/v1/workflows` | 注册新流程 |
| DELETE | `/api/v1/workflows/{workflow_id}` | 删除流程 |
| GET | `/api/v1/runs` | 获取任务列表 (分页) |
| POST | `/api/v1/runs` | 提交新任务 |
| GET | `/api/v1/runs/{run_id}` | 获取任务详情 |
| POST | `/api/v1/runs/{run_id}/resume` | 断点续跑 |
| POST | `/api/v1/runs/{run_id}/retry` | 重试失败任务 |
| POST | `/api/v1/runs/{run_id}/cancel` | 取消任务 |
| GET | `/api/v1/images` | 获取镜像列表 |
| POST | `/api/v1/images/pull` | 拉取镜像 |
| DELETE | `/api/v1/images/{image_id}` | 删除本地镜像 |
| GET | `/api/v1/events/stream?project_id=...` | SSE 实时事件流 |
| GET | `/api/v1/agent/conversations?project_id=...` | 获取对话列表 |
| GET | `/api/v1/agent/conversations/{conversation_id}` | 获取对话历史 |
| POST | `/api/v1/agent/conversations` | 新建对话（计划） |
| GET | `/api/v1/agent/conversations/{conversation_id}/trace` | Agent 调试/Trace（计划） |
| POST | `/api/v1/workflows/register-demo` | Demo 一键注册（计划） |
