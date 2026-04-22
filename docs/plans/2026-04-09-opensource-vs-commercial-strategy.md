# Bioinfoflow — 战略全景文档

**日期**: 2026-04-09
**状态**: 战略参考文档（持续更新）

## Context

Lewis 是 Bioinfoflow 的 solo founder，拥有 Bio + CS 跨领域背景，是 Nextflow/WDL 的 domain expert。目前有 3-6 个月 runway，有表示兴趣但尚未活跃使用的潜在用户，尚无付费用户。本文档覆盖：愿景宣言、产品路线图、开源 vs 商业化策略、功能分层、营销策略。

---

## Manifesto — 我们相信什么

### 生物数据是人类的公共财富，不是少数公司的护城河。

今天的生物信息学被三堵墙困住：

**分析之墙** — Pipeline 配置像在写密码。一个 nf-core/rnaseq 的 nextflow.config 有 136 个参数。每次换一个新 pipeline，研究者要花 3 天调参数、debug 错误消息。真正的科学发现被淹没在运维工作中。

**工具之墙** — 现有的 workflow 管理平台要么锁定你在他们的 cloud 上（Terra, DNAnexus），要么需要专业 DevOps 团队来维护（Nextflow Tower）。小实验室、独立研究者、发展中国家的科学家被排除在外。

**数据之墙** — 全球每天产生 PB 级基因组数据，但绝大部分锁在各机构的存储阵列里，互不可见、互不可用。同一种罕见病的数据分散在 50 个医院，没有人能把它们汇在一起做有意义的分析。基因组数据的价值在于规模——1000 个样本的发现远超 10 个样本的总和——但我们的基础设施让共享比孤立更难。

**Bioinfoflow 的使命**：拆掉这三堵墙。

### 我们的原则

1. **Local-First, Cloud-Ready** — 你的数据默认留在你的机器上。你选择何时、以何种方式使用云资源。没有 vendor lock-in，没有 egress 费用陷阱。

2. **AI 是同事，不是黑盒** — AI 应该像一个经验丰富的生信工程师坐在你旁边：你可以向它提问、让它帮你配置、debug、解读结果。但它所做的一切都是透明的、可审计的、可以被人类覆盖的。

3. **工具服务于科学家，不是反过来** — 一个从来没用过命令行的 PI 应该能在 5 分钟内提交一个 WGS 分析。一个经验丰富的生信工程师应该能完全控制每一个参数。同一个工具，不同的深度。

4. **数据属于产生它的人** — 机构拥有管理权，个人拥有主权。未来，当我们建立数据共享网络时，每一次访问都是透明的、经过授权的、有经济激励的。

5. **科学不应该有国界** — 一个基因突变不会因为它被发现在非洲还是美国而改变意义。我们的工具和数据网络从第一天就是全球化的。

---

## Manifestation — 愿景如何落地

### 今天（Phase 1: 工具层）— "让每个实验室拥有世界级的分析能力"

| 能力 | 如何体现原则 |
|------|-------------|
| **AI Agent** | 自然语言 → pipeline 配置 → 验证 → 运行 → 解读报告。拆掉"分析之墙"。 |
| **Docker Compose 一键部署** | 任何有 Docker 的机器 5 分钟跑起来。拆掉"工具之墙"。 |
| **双引擎 (Nextflow + WDL)** | 不锁定引擎选择。 |
| **消费级 GPU 支持** | RTX 4080 Super 也能跑 WGS。拆掉"硬件之墙"。 |
| **渐进式 UI** | PI 看到简洁界面，工程师看到完整控制台。 |

### 明天（Phase 2: 协作层）— "让团队共享分析能力"

| 能力 | 如何体现原则 |
|------|-------------|
| **团队工作区** | 多人协作、RBAC、审计日志。 |
| **远程执行** | 本地提交 → SSH 到 HPC / cloud burst。 |
| **Mobile 监控** | 手机通知、报告查看、远程控制。 |

### 后天（Phase 3: 数据层）— "让全球的生物数据自由流动"

| 能力 | 如何体现原则 |
|------|-------------|
| **Federated Data Index** | 数据留在本地，只索引元数据。数据不动，查询在动。 |
| **Consent-Based Access** | 数据持有者设定规则，每次查询触发授权。 |
| **Programmatic Micropayments** | 按需付费，费用流向数据贡献者。基于 x402 协议。 |
| **匿名化 + 差分隐私** | 个体级数据永远不暴露。 |

---

## Web3 愿景战略分析

### 核心洞察：你要的不是 "Web3"，你要的是 "数据主权 + 程序化支付"

**历史教训**：
- Luna DNA (Illumina Ventures 投资) — 2024 年 1 月关停
- Nebula Genomics (George Church 背书) — Trustpilot 评分从 3.1 降到 1.7
- 错误：把"区块链"当成了产品，而不是基础设施

**x402 协议：更务实的路径** — HTTP 原生支付标准，已被 Stripe/AWS/Coinbase/Cloudflare/Vercel 采纳，7500 万+ 交易。AI agent 发起 HTTP 请求 → 收到 402 → 自动支付 → 获取数据。零摩擦，合规友好。

### 表述策略：渐进式揭示

- Phase 1：**local-first, data sovereignty, no vendor lock-in**
- Phase 2：**federated, data commons, global discovery**
- Phase 3：**programmatic access, fair compensation, consent-based**
- **永远不用的词**：blockchain, token, Web3, DAO, decentralized, mining, staking

---

## Roadmap — 产品路线图

### Phase 1: Foundation (现在 → 6 个月)

```
Q2 2026 (现在)
├── ✅ AI Agent Runtime v2
├── ✅ 双引擎 (Nextflow + WDL)
├── ✅ GPU 检测 + Parabricks 支持
├── ✅ DAG 可视化 + CLI 工具
├── 🔄 Docker Compose 一键部署
├── 📋 nf-core AI 配置助手 (MVP)
├── 📋 消费级 GPU WGS 演示 + benchmark
└── 📋 找到 5 个 design partner

Q3 2026
├── 📋 Telegram/Email 通知渠道
├── 📋 PWA 手机版 (基础监控)
├── 📋 GitHub public repo (BSL 1.1)
├── 📋 社交媒体内容启动
└── 📋 10 个活跃用户
```

### Phase 2: Growth (6-18 个月)

```
Q4 2026 - Q1 2027
├── 📋 Pro Edition (RBAC + 团队 + 审计)
├── 📋 HPC 远程执行
├── 📋 高级 scheduler (GPU 亲和性)
├── 📋 Mobile 完整体验
├── 📋 首批付费用户
└── 📋 考虑 YC W27

Q2-Q3 2027
├── 📋 Enterprise Edition (SSO + 合规)
├── 📋 Cloud burst
├── 📋 托管 SaaS beta
├── 📋 第一轮融资
└── 📋 100+ 活跃用户
```

### Phase 3: Platform (18-36 个月)

```
2028
├── 📋 Federated Data Index
├── 📋 Consent Management
├── 📋 x402 micropayments 集成
├── 📋 匿名化 + 差分隐私层
└── 📋 Series A

2029+
├── 📋 全球数据发现网络
├── 📋 AI 跨机构 meta-analysis
└── 📋 "全球生物数据公共基础设施"
```

### 关键里程碑

| 里程碑 | 衡量标准 | 预计时间 |
|--------|---------|---------|
| First 5 users | 5 人真实使用 | 2026 Q2 |
| Public launch | GitHub + 社区 | 2026 Q3 |
| First paying customer | $1 ARR | 2026 Q4 |
| PMF signal | 40%+ "very disappointed" | 2027 Q1 |
| $100K ARR | ~170 Pro seats | 2027 Q3 |
| Data layer launch | First federated query | 2028 Q2 |

---

## 一、YC 视角下的冷静评估

### 你有什么
- **扎实的产品工程**：Full-stack platform (FastAPI + Next.js 16)，AI agent、priority scheduler、dual-engine (Nextflow + WDL)、DAG 可视化、CLI 工具——功能完成度高
- **稀缺的交叉背景**：同时懂生信 pipeline 痛点 + 能写 production-grade 软件的人非常少
- **AI coding leverage**：Claude Code + Codex 让一个人能维持这个体量的代码库

### YC 会问的致命问题
1. **"Who are your users and do they love it?"** — 你现在没有活跃用户。这是 YC 最看重的信号。
2. **"Why hasn't anyone started using it?"** — 产品做了很多，但没有跑通 distribution。
3. **"What's your unfair advantage?"** — Domain expertise 是一个，但 Seqera (Nextflow Tower) 有 $52M 融资 + Nextflow 核心团队。

### 残酷现实
YC 更喜欢 "做了很少但有很多用户" 的项目，而不是 "做了很多但没有用户" 的项目。你需要先证明 PMF (Product-Market Fit)，才能谈 open-source strategy。

---

## 二、三条路线对比

### 路线 A：完全开源 (MIT/Apache 2.0)
**核心逻辑**：先用开源获取用户 → 建立社区 → 然后找商业模式

| 优势 | 劣势 |
|------|------|
| 降低用户尝试门槛（免费、可审计）| 没有护城河，大公司可以 fork |
| 生信领域信任开源工具 | Solo founder 维护社区的时间成本巨大 |
| 可以吸引贡献者帮你做功能 | 贡献者通常比你想象的少得多 |
| 符合学术/机构的采购习惯 | 从开源到赚钱的路很长 |

**适合场景**：你有其他收入来源，或者你的首要目标是建立个人品牌/影响力。

**风险**：3-6 个月 runway 不够等到社区起来。开源项目获取 star 容易，获取 active contributor 很难。

### 路线 B：Open-Core (推荐)
**核心逻辑**：核心引擎开源 → 企业功能付费 → 开源获客 + 付费变现

**开源部分 (Community Edition)**：
- 单用户模式（personal mode）
- 基础 scheduler
- Nextflow + WDL 引擎适配
- CLI 工具
- AI agent 基础能力
- Docker Compose 部署

**付费部分 (Pro/Enterprise)**：
- 多用户 + RBAC + 团队协作（已 scaffold: workspace/membership models）
- SSO / SAML 集成
- 审计日志 + 合规报告（audit log model 已有）
- 高级 scheduler（GPU 调度、backfill 优化）
- 远程执行（SSH to HPC/cloud）
- 优先技术支持
- 托管 SaaS 版本

| 优势 | 劣势 |
|------|------|
| 开源部分降低获客成本 | 需要维护两个版本的复杂度 |
| 付费功能对标企业预算 | 需要想清楚开源/付费的边界 |
| YC 熟悉这个模式（GitLab, Sentry, PostHog）| 早期可能两边都不讨好 |
| 企业客户习惯为 "团队/合规" 付费 | Core facility / pharma 销售周期长 |

**适合场景**：你想走 VC 路线或建立可持续的 SaaS 业务。

### 路线 C：先闭源，验证 PMF，再决定
**核心逻辑**：先找到 5-10 个付费用户 → 证明 PMF → 再决定开源策略

| 优势 | 劣势 |
|------|------|
| 速度最快——不用花时间在社区维护上 | 失去开源的 distribution 优势 |
| 可以灵活调整产品方向 | 生信用户对闭源工具天然不信任 |
| 先赚到钱再说 | 竞争对手（Seqera）已经开源 |

**适合场景**：你有明确的 beta 用户渠道，能快速做 sales。

---

## 三、建议：先做 Distribution，再谈 Open-Source Strategy

### 核心观点
**你现在的问题不是 "开源还是闭源"，而是 "怎么让第一批人用起来"。**

开源策略是一个 distribution 工具，不是目的。在你没有用户的情况下，开源代码 = 把代码放在 GitHub 上无人问津。

### 具体建议（按优先级排序）

#### Step 1：找到 5 个 Design Partner (本周就开始)
- 回到你的学术网络：以前的实验室同事、导师、同行
- 不卖产品，卖 "帮你跑 pipeline" 的服务
- 亲自帮他们部署，坐在旁边看他们用
- **目标**：5 个人在实际工作中用 Bioinfoflow 跑了真实的 pipeline

#### Step 2：Docker Compose 打包 (当前 plan)
- 这是对的——降低部署门槛是获取用户的前提
- 但不要只做技术，做完后立刻给 design partner 部署

#### Step 3：选择一个切入点，做到极致
你的产品功能太多了。YC 创始人常犯的错误是 "做了一个 platform"。建议选择一个 killer use case：

**推荐切入点：nf-core pipeline 的 AI 助手**
- nf-core 社区庞大（100+ 标准化 pipeline）
- 现有用户痛点明确：配置参数复杂、debug 困难
- 你的 AI agent + schema extraction 天然适合这个场景
- 可以做成 "ChatGPT for nf-core" 的叙事

#### Step 4：根据 traction 决定模式
- 如果 5 个 design partner 中有 2+ 个愿意付费 → 走路线 B (Open-Core)
- 如果用户增长快但没人付费 → 走路线 A (全开源 + 融资)
- 如果找不到 design partner → 重新审视产品方向

---

## 四、如果走 YC 申请路线

### Timeline
- YC S26 batch (Summer 2026) 申请通常在 3-4 月，面试在 5-6 月
- 如果目标是 W27 (Winter 2027)，你有 ~8 个月准备

### YC 申请需要展示的
1. **Traction > Tech**：5+ active users > 完美的代码
2. **Speed**：从 0 用户到有人在用的速度
3. **Founder-Market Fit**：你的 Bio + CS 背景是强项，讲好这个故事
4. **Market Size**：Bioinformatics tools market ~$3B+，但你要讲清楚你的 wedge

### YC 喜欢的叙事
> "我是一个做了 10 年生信分析的人，每次配置 Nextflow pipeline 都要花 3 天 debug 参数。我做了一个 AI 助手，现在 X 个实验室在用，平均把 pipeline setup 时间从 3 天降到 30 分钟。"

注意：这个叙事需要真实数据支撑。

---

## 五、License 建议

如果你决定开源（路线 A 或 B），推荐：

| License | 适用场景 |
|---------|---------|
| **BSL (Business Source License)** | 最推荐——代码公开可审计，但禁止竞争对手提供托管服务。N 年后自动转 Apache 2.0。MariaDB, Sentry, CockroachDB 用这个。 |
| **AGPL-3.0** | 强迫使用者开源修改。适合阻止 AWS 等大厂白嫖。但会吓跑一些企业用户。 |
| **Apache 2.0** | 最宽松，适合最大化社区采纳。但没有任何商业保护。 |
| **Dual License** | Community (AGPL) + Commercial (付费)。GitLab 模式。 |

**推荐**：BSL 1.1 (类似 Sentry, HashiCorp)。代码完全公开，用户可以自由自部署，但不允许第三方卖你的托管服务。3 年后自动转 Apache 2.0。

---

## 六、竞争格局

| 维度 | Bioinfoflow | Seqera (Tower) | Terra | DNAnexus |
|------|-------------|----------------|-------|----------|
| **数据主权** | 本地优先 (你的) | 云端 (他们的) | 云端 (他们的) | 云端 (他们的) |
| **成本模型** | 免费 (自托管) | Freemium | 按用量付费 | 按用量付费 |
| **供应商锁定** | 无 | 中等 | 高 | 高 |
| **AI Agent** | 原生 (LLM驱动) | 无 | 无 | 无 |
| **工作流引擎** | Nextflow + WDL | 仅 Nextflow | Cromwell | 自研 |
| **融资** | 0 | $52M | Google | Roche等 |
| **社区** | 早期 | 中等 | 大 | 企业级 |

**关键差异化**：AI agent + 双引擎 + 本地优先。这三个结合在一起是独特的。

---

## 七、行动优先级总结

| 优先级 | 行动 | 时间 |
|--------|------|------|
| P0 | 找 5 个 design partner，让他们用起来 | 本周 |
| P0 | 完成 Docker Compose 打包（降低部署门槛）| 本周 |
| P1 | 选择一个 killer use case (推荐: nf-core AI 助手) | 2 周内 |
| P1 | 上线 GitHub public repo (BSL license) | 有 3+ active users 后 |
| P2 | 根据 traction 数据决定 Open-Core 边界 | 1-2 个月后 |
| P3 | 考虑 YC 申请 | 有 10+ active users 后 |

**核心原则：先有用户，再谈策略。没有 PMF 的开源 = 没有观众的演出。**

---

## 八、Killer Use Case 分析与排序

### Tier 1：高 PMF 潜力（优先做）

#### 1. nf-core AI 助手 — 最推荐
**痛点**：nf-core 有 100+ 标准化 pipeline，配置参数复杂（`nextflow_schema.json` 动辄 200+ 参数），debug 困难。

**已有基础**：AI Agent Runtime v2 + WorkflowValidateTool + SchemaExtractor + PubMedSearchTool + WebSearchTool + ShellTool。大部分能力已经就位。

**叙事**："ChatGPT for nf-core" — 自然语言 → 自动生成参数配置 → 验证输入 → 监控运行 → 解读报告。

**市场**：nf-core Slack 5000+ 成员，精准、活跃、有明确痛点。

#### 2. 消费级 GPU 跑 Parabricks WGS — 差异化最强
**痛点**：Parabricks 官方只支持 A100/V100，但小型实验室常有 RTX 4080 Super (16GB VRAM)。

**已有基础**：GpuService（完整 NVIDIA 检测）、GPU_PIPELINE_PATTERNS 自动识别、consumer_gpu profile 自动应用、PARABRICKS_MIN_VRAM_MB=16000 兼容检查、resource monitoring。

**叙事**："RTX 4080 Super + 30 分钟 = 30x WGS。不需要 AWS，不需要 A100。"

**风险**：需确认 Parabricks EULA 是否限制消费级 GPU。

### Tier 2：高价值但需要更多开发

#### 3. 手机远程控制 + 通知 + 报告推送
**已有基础**：SSE EventBus（per-project subscription）、完整事件类型、responsive 前端（useIsMobile hook）、NotificationConfig model（webhook channel）。

**建议分层实施**：
- Layer 1（低成本）：扩展 NotificationService 支持 Telegram/Slack/Email channel
- Layer 2（中等）：PWA（service worker + Web Push API）
- Layer 3（长期）：原生 mobile app（过早优化，不推荐现在做）

### Use Case 优先级

| 优先级 | Use Case | 开发量 | PMF 信号 | 差异化 |
|--------|----------|--------|----------|--------|
| P0 | nf-core AI 助手 | 低 | 高 | 中 |
| P0 | Parabricks 消费级 GPU | 低 | 中 | 高 |
| P1 | Telegram/Email 通知 | 低 | 中 | 低 |
| P1 | PWA 手机版 | 中 | 中 | 中 |
| P2 | MultiQC AI 解读 | 中 | 中 | 中 |
| P3 | 原生 Mobile App | 高 | 低 | 低 |

---

## 九、Open-Core 功能分层与定价

### 架构分离就绪度

**关键发现：代码库天然适合 Open-Core 分离**
- `AUTH_MODE` 环境变量（dev/personal/team）= 天然 feature gate
- Workspace scoping 已有（所有 API 按 workspace_id 隔离）
- AuditLog model + audit_repo 已建
- NotificationConfig 有 channel 字段，扩展容易

### 功能分层

**Community（免费，BSL 1.1）**：单用户模式、基础 scheduler、双引擎、AI Agent 基础、CLI、Docker Compose、Webhook 通知、DAG 可视化

**Pro（$49/user/month，年付 $39）**：多用户 RBAC、团队协作、审计日志、高级 scheduler（GPU 调度）、多通知渠道、报告 PDF export

**Enterprise（联系销售）**：SSO/SAML、合规报告（GxP）、远程 HPC/Cloud 执行、白标、SLA 支持、托管 SaaS

### 架构实现方式

推荐 GitLab 模式：同一代码库 + `BIOINFOFLOW_EDITION` 环境变量 + edition check 装饰器。不拆分 repo，不维护两个版本。分离难度：**低到中等**。

### 定价原则
1. 按 seat 收费（不按计算量）— 价值是 "管理更简单"，不是计算资源
2. 学术机构 50% 折扣 — 这是 distribution 工具
3. 年付 20% 折扣 — 降低 churn
4. 免费层要真正好用 — Community Edition 必须能独立解决问题，不是残疾版

---

## 十、社交媒体获客策略

### 三种内容类型

1. **痛点共鸣帖（40%）**：生信日常痛苦 → 引起共鸣 → 高传播
2. **技术演示帖（30%）**：30-60 秒 GIF/视频 → 展示产品能力 → 高转化
3. **知识分享帖（30%）**：Nextflow vs WDL 比较、本地 vs cloud 分析 → 建立专家权威

### 发布节奏

| 平台 | 频率 | 重点 |
|------|------|------|
| Twitter/X | 每天 1-2 条 | 痛点 + 演示 + 知识 |
| LinkedIn | 每周 2-3 条 | 行业洞察 + 知识分享 |
| Reddit r/bioinformatics | 每周 1 条 | 纯价值内容 |
| nf-core Slack | 随时 | 帮人解决问题 |
| 知乎 / WeChat 公众号 | 每周 1-2 条 | 中文生信社区 |

### 核心原则
- 80% 价值 / 20% 推广
- 截图/视频优先
- 中英双语（中文生信社区同样重要）
- 个人品牌 = 产品品牌（solo founder 阶段）
- 回复每一条评论
