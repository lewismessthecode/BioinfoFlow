# Bioinfoflow — 战略全景文档

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

Bioinfoflow 首先是一个**本地优先的生信 workflow 管理平台**：

| 能力 | 如何体现原则 |
|------|-------------|
| **AI Agent** | 自然语言 → 自动生成 pipeline 配置 → 验证 → 运行 → 解读报告。拆掉"分析之墙"。 |
| **Docker Compose 一键部署** | 任何有 Docker 的机器都能在 5 分钟内跑起来。拆掉"工具之墙"。 |
| **双引擎 (Nextflow + WDL)** | 不锁定引擎选择。你的 pipeline 在哪个引擎跑，你说了算。 |
| **消费级 GPU 支持** | RTX 4080 Super 也能跑 WGS。拆掉"硬件之墙"。 |
| **渐进式 UI** | PI 看到简洁界面，生信工程师看到完整控制台。同一个工具，不同深度。 |

### 明天（Phase 2: 协作层）— "让团队共享分析能力"

| 能力 | 如何体现原则 |
|------|-------------|
| **团队工作区** | 多人协作、RBAC、审计日志。从个人工具变成实验室基础设施。 |
| **远程执行** | 本地提交 → SSH 到 HPC / cloud burst。计算资源在你手里。 |
| **Mobile 监控** | 在手机上收到分析通知、查看报告。分析不再绑定在桌面。 |

### 后天（Phase 3: 数据层）— "让全球的生物数据自由流动"

这是最远大、也最需要谨慎推进的层次。

| 能力 | 如何体现原则 |
|------|-------------|
| **Federated Data Index** | 各机构的数据留在本地，Bioinfoflow 只索引元数据（物种、样本类型、测序平台、表型标签）。数据不动，查询在动。 |
| **Consent-Based Access** | 数据持有者设定访问规则。每次查询触发授权流程。完全透明，完全可审计。 |
| **Programmatic Micropayments** | 企业/机构需要使用数据时，通过 API 发起请求，按需付费。费用流向数据贡献者。使用 x402 协议（HTTP 402 原生支付标准，Stripe/AWS/Coinbase 已支持）实现零摩擦支付。 |
| **匿名化 + 差分隐私** | 个体级数据永远不会暴露。查询返回的是聚合统计或差分隐私处理后的结果。 |

---

## 关于 Web3 愿景的战略分析

### 核心洞察：你要的不是 "Web3"，你要的是 "数据主权 + 程序化支付"

**历史教训**：
- **Luna DNA** (Illumina Ventures 投资) — 2024 年 1 月关停，原因："capital is very difficult to access"。区块链叙事没有帮它找到 PMF。
- **Nebula Genomics** (George Church 背书) — 仍在运营但 Trustpilot 评分从 3.1 降到 1.7。区块链没有解决核心用户体验问题。

**它们的错误**：把"区块链"当成了产品，而不是基础设施。用户不关心数据存在哪条链上，用户关心的是："我的数据安全吗？谁在用？我能从中受益吗？"

### x402 协议：比 Web3 更务实的路径

x402 不是 crypto/Web3 项目——它是一个 **HTTP 原生支付标准**，基于从未被使用过的 HTTP 402 状态码。已经被 Stripe、AWS、Coinbase、Cloudflare、Vercel 采纳。2026 年至今已处理 7500 万+ 交易。

**为什么 x402 比区块链更适合你的场景**：
1. **零摩擦**：AI agent 发起 HTTP 请求 → 收到 402 → 自动支付 → 获取数据。不需要钱包、不需要 gas fee
2. **合规友好**：稳定币 (USDC) 支付，有清晰的法律框架。不涉及 token 发行
3. **企业可接受**：Stripe 和 AWS 都在推。CIO 不会因为你用了 x402 而拒绝你
4. **与现有架构兼容**：你的 FastAPI 加一个 middleware 就能支持

### 应该暴露多少 "去中心化" 愿景？

| 策略 | 风险 | 适合阶段 |
|------|------|---------|
| **完全不提** | 失去差异化叙事 | Phase 1（现在）|
| **用 "Data Sovereignty" 而非 "Web3" 表述** ⭐推荐 | 几乎没有风险 | Phase 1-2 |
| **提 "Federated Data Commons"** | 低风险，学术界认可 | Phase 2 |
| **提 "x402 programmatic micropayments"** | 中等风险（有人会联想到 crypto）| Phase 3 |
| **大谈 "Web3 + 去中心化 + token economics"** | 高风险（大公司警惕、监管不确定、学术界排斥）| 不推荐 |

### 推荐表述策略：渐进式揭示

**Phase 1 对外叙事**：
> "Bioinfoflow 是一个本地优先的生信 workflow 平台。你的数据留在你的机器上，你完全控制你的分析。"
> — 关键词：**local-first, data sovereignty, no vendor lock-in**

**Phase 2 对外叙事**：
> "Bioinfoflow 正在建立 Federated Data Index——各机构的数据留在本地，但元数据可以被全球发现。像 Google Scholar 做论文索引一样，我们做生物数据索引。"
> — 关键词：**federated, data commons, global discovery**

**Phase 3 对外叙事**：
> "企业和机构可以通过 API 付费访问联邦数据网络。每次查询都是透明的、经过授权的。数据贡献者获得公平的经济回报。"
> — 关键词：**programmatic access, fair compensation, consent-based**

**注意：永远不用的词**：blockchain, token, Web3, DAO, decentralized (用 "federated" 代替), mining, staking

### 法律和竞争阻力分析

| 风险 | 评估 | 缓解措施 |
|------|------|---------|
| **GDPR/HIPAA 合规** | 中等 — 只要数据不跨境移动，federated 模式天然合规 | 数据不动，查询在动；差分隐私 |
| **大公司竞争** | 低（短期）— Illumina/Roche/Thermo 不做开源 workflow 工具 | 先做工具层，数据层是 5 年后的故事 |
| **学术机构 IRB 审批** | 中等 — 任何数据共享都需要 IRB 批准 | 设计时内置 consent 管理；与 IRB 流程兼容 |
| **Token 发行法律风险** | 高 — 如果发 token，在美国可能被视为证券 | **不发 token**。用 x402 + USDC 稳定币 |
| **数据定价争议** | 中等 — 谁来定价？如何确保公平？| 市场定价 + 社区治理（类似 HuggingFace datasets）|

---

## Roadmap — 产品路线图

### Phase 1: Foundation (现在 → 6 个月)
**目标**：5-20 个活跃用户，验证 PMF

```
Q2 2026 (现在)
├── ✅ AI Agent Runtime
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
├── 📋 nf-core Slack/Twitter 社区运营
└── 📋 10 个活跃用户
```

### Phase 2: Growth (6-18 个月)
**目标**：100+ 用户，10+ 付费用户，Open-Core 模式上线

```
Q4 2026 - Q1 2027
├── 📋 Pro Edition 发布 (RBAC + 团队 + 审计)
├── 📋 HPC 远程执行 (SSH adapter)
├── 📋 高级 scheduler (GPU 亲和性 + backfill)
├── 📋 Mobile 完整体验 (通知 + 报告 + 控制)
├── 📋 MultiQC AI 解读
├── 📋 考虑 YC W27 申请
└── 📋 首批付费用户

Q2-Q3 2027
├── 📋 Enterprise Edition (SSO + 合规)
├── 📋 Cloud burst (AWS/GCP 弹性计算)
├── 📋 托管 SaaS 版本 beta
├── 📋 第一轮融资 (pre-seed / seed)
└── 📋 100+ 活跃用户
```

### Phase 3: Platform (18-36 个月)
**目标**：成为生信基础设施，启动数据层

```
2028
├── 📋 Federated Data Index (元数据索引)
├── 📋 Consent Management System
├── 📋 x402 programmatic micropayments 集成
├── 📋 匿名化 + 差分隐私层
├── 📋 首批数据贡献机构
└── 📋 Series A

2029+
├── 📋 全球数据发现网络
├── 📋 AI-powered 跨机构 meta-analysis
├── 📋 研究者经济激励体系
└── 📋 "全球生物数据公共基础设施"
```

### Roadmap 关键里程碑

| 里程碑 | 衡量标准 | 预计时间 |
|--------|---------|---------|
| **First 5 users** | 5 人在真实工作中使用 | 2026 Q2 |
| **Public launch** | GitHub repo + 社区 | 2026 Q3 |
| **First paying customer** | $1 ARR | 2026 Q4 |
| **PMF signal** | 40%+ users say "very disappointed" if product gone | 2027 Q1 |
| **YC application** | 10+ active, 3+ paying | 2027 W batch |
| **$100K ARR** | ~170 Pro seats or 5 Enterprise | 2027 Q3 |
| **Data layer launch** | First federated data query | 2028 Q2 |

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
- 多用户 + RBAC + 团队协作（你已经 scaffold 了 workspace/membership）
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

## 三、我的建议：先做 Distribution，再谈 Open-Source Strategy

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

**我的推荐**：BSL 1.1 (类似 Sentry, HashiCorp)。代码完全公开，用户可以自由自部署，但不允许第三方卖你的托管服务。3 年后自动转 Apache 2.0。

---

## 六、总结

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

## 七、Killer Use Case 分析与排序

### Tier 1：高 PMF 潜力（优先做）

#### 1. nf-core AI 助手 ⭐ 最推荐
**痛点**：nf-core 有 100+ 标准化 pipeline，但配置参数复杂（`nextflow_schema.json` 动辄 200+ 参数），debug 困难，新手入门曲线陡峭。

**你已经有的**：
- AI Agent Runtime（async loop + tool dispatch）
- `WorkflowValidateTool` — 可以验证 Nextflow/WDL 工作流
- `SchemaExtractor` — 自动从 nf-core 提取参数 schema
- `PubMedSearchTool` + `WebSearchTool` — 科研上下文检索
- `ShellTool` + `FileReadTool` — 自动化 debug

**叙事**："ChatGPT for nf-core" — 用自然语言描述你的样本和分析需求，AI 自动生成正确的参数配置、验证输入、监控运行、解读报告。

**市场大小**：nf-core Slack 有 5000+ 成员，每月数千次 pipeline 运行。这是一个精准、活跃、有痛点的社区。

**执行路径**：
1. 先做 nf-core/rnaseq 和 nf-core/sarek 两个最热门 pipeline 的 AI 配置助手
2. 发到 nf-core Slack #general 和 Twitter，配一个 30 秒演示视频
3. 收集反馈 → 迭代

#### 2. 消费级 GPU 跑 Parabricks WGS ⭐ 差异化明显
**痛点**：Parabricks 官方只支持 A100/V100 等数据中心 GPU，但很多小型实验室有 RTX 4080 Super (16GB VRAM)。目前没有工具帮他们轻松在消费级 GPU 上跑 WGS。

**你已经有的**：
- `GpuService` — 完整的 NVIDIA 检测（nvidia-smi）、Apple Silicon 检测、Docker NVIDIA runtime 检查
- Nextflow 适配器中的 `GPU_PIPELINE_PATTERNS` — 自动识别 parabricks/wgs-nf/clara-parabricks
- `consumer_gpu` profile 自动应用
- `PARABRICKS_MIN_VRAM_MB = 16000` — 16GB VRAM 兼容性检查
- Scheduler 的 resource monitoring（CPU/mem/disk/GPU metrics）

**叙事**："在你的 RTX 4080 Super 上用 30 分钟跑完一个 30x WGS，不需要 AWS，不需要 A100。"

**市场**：小型基因组学实验室、临床小团队、个人研究者。这些人买不起/用不起 A100，但有 gaming GPU。

**风险**：Parabricks license 限制。需要确认 NVIDIA 是否允许消费级 GPU 运行 Parabricks（目前 Parabricks 4.0+ 对学术免费，但 EULA 可能限制 GPU 类型）。

### Tier 2：高价值但需要更多开发

#### 3. 手机远程控制（Claude Code Dispatch 模式）
**痛点**：生信分析经常跑几小时到几天。研究人员不想一直坐在电脑前等。能在手机上监控、获取通知、甚至启动新分析是强需求。

**你已经有的**：
- SSE EventBus（per-project subscription，200 事件队列）
- 完整的事件类型（`run.status`, `run.log`, `run.dag`, `agent.*`）
- SSE streaming endpoint `/events/stream`
- 前端已有 responsive 设计（`useIsMobile()` hook，mobile drawer）
- 通知模型 `NotificationConfig`（目前仅 webhook channel）

**还需要做的**：
- PWA 支持（service worker + manifest.json + Web Push API）
- 或者：原生 mobile app（React Native / Flutter）
- 通知渠道扩展（从 webhook → push notification / email / Telegram）
- 后台 SSE 持久连接（手机后台限制）

**建议**：先做 PWA（成本最低），不要一开始做原生 app。PWA 可以收到 push notification，可以 add to home screen，对生信用户够用。

**叙事**："在实验室提交分析，在地铁上收到结果通知，在咖啡厅查看报告。"

#### 4. 手机通知 + 手机推送报告
**这和 #3 是同一个 feature 的不同层次**：
- **Layer 1 (简单)**：Webhook → Telegram bot / Slack bot / Email。你的 `NotificationService` 已经有 webhook，只需要加 channel 类型。
- **Layer 2 (中等)**：PWA Push Notification（需要 service worker + VAPID keys）
- **Layer 3 (高级)**：报告生成 + PDF export + 推送。需要新的 report service。

**执行建议**：先做 Layer 1（加 Telegram/Slack/Email 通知渠道），这是最低成本、最高价值的改动。`NotificationConfig` 模型已经有 `channel` 字段和 JSON `config`，扩展很容易。

### Tier 3：长期差异化

#### 5. MultiQC 报告 AI 解读
**痛点**：MultiQC 报告很长，新手不知道哪些指标异常，该如何处理。

**叙事**："上传 MultiQC 报告，AI 告诉你哪些样本有问题，为什么，以及如何修复。"

**策略**：这可以作为 AI Agent 的一个高级 tool，不需要大量新开发。

### Use Case 优先级排序

| 优先级 | Use Case | 开发量 | PMF 信号 | 差异化 |
|--------|----------|--------|----------|--------|
| P0 | nf-core AI 助手 | 低（大部分已有） | 高（社区大、痛点明确）| 中（别人可以做） |
| P0 | Parabricks 消费级 GPU | 低（GPU stack 已有）| 中（受众窄但痛点深）| 高（没人做过） |
| P1 | Telegram/Email 通知 | 低（扩展 channel）| 中 | 低 |
| P1 | PWA 手机版 | 中 | 中 | 中 |
| P2 | MultiQC AI 解读 | 中 | 中 | 中 |
| P3 | 原生 Mobile App | 高 | 低（过早优化）| 低 |

---

## 八、Open-Core 功能分层与定价策略

### 基于代码库的分层建议

#### Community Edition (免费，BSL 1.1)

| 功能 | 现有代码状态 |
|------|-------------|
| 单用户模式（personal mode）| ✅ 已实现（`AUTH_MODE=personal`）|
| 基础 scheduler（FIFO，单队列）| ✅ 已实现（SlotTracker + PriorityQueue）|
| Nextflow + WDL 双引擎 | ✅ 已实现（适配器模式）|
| AI Agent 基础能力（对话、文件操作）| ✅ 已实现（默认 Agent Runtime + 10+ tools）|
| CLI 工具（bif）| ✅ 已实现（HTTP-only client）|
| Docker Compose 一键部署 | 🔄 进行中 |
| Webhook 通知 | ✅ 已实现 |
| DAG 可视化 | ✅ 已实现（React Flow）|
| 工作流参数提取 | ✅ 已实现（SchemaExtractor）|

#### Pro Edition ($49-99/user/month)

| 功能 | 现有代码状态 | 分离难度 |
|------|-------------|---------|
| 多用户 + RBAC | ✅ 模型已有（Workspace, WorkspaceMembership, role 字段）| **低** — `AUTH_MODE=team` 切换即可 |
| 团队协作（共享 workspace）| ✅ 模型已有（workspace_id on Project）| **低** — 已有 workspace scoping |
| 审计日志 | ✅ 模型+仓库已有（AuditLog + audit_repo）| **低** — 加 UI + export |
| 高级 scheduler（优先级、GPU 调度）| ✅ 基础已有（weight, priority, GPU detection）| **中** — 需要 GPU 亲和性调度 |
| 高级 AI Agent（多轮对话、workflow 编排）| ✅ 基础已有 | **中** — 需要 usage quota |
| 多通知渠道（Email/Slack/Telegram）| 🔨 需要扩展 NotificationService | **低** |
| 报告生成 + PDF export | ❌ 需新建 | **中** |

#### Enterprise Edition (联系销售，$500+/user/month 或年度合同)

| 功能 | 现有代码状态 | 分离难度 |
|------|-------------|---------|
| SSO / SAML 集成 | ❌ 需新建（Better Auth 有 enterprise plugin）| **高** |
| 合规报告（GxP, 21 CFR Part 11）| ❌ 需新建 | **高** |
| 远程执行（SSH to HPC/Cloud）| ❌ 需新建 | **高** |
| 白标部署 | ❌ 需新建 | **中** |
| 优先技术支持 + SLA | 不需要代码 | **无** |
| 托管 SaaS 版本 | 需要 infra | **高** |

### 架构分离方案

#### 你的架构天然适合 Open-Core

**关键发现**：你的代码库已经有了 Open-Core 分离的核心基础设施：

1. **Auth Mode 作为 Feature Gate**：`AUTH_MODE` 环境变量（dev/personal/team）天然区分了单用户和多用户模式。Community = `personal`，Pro = `team`。
2. **Workspace Scoping**：所有 API 查询已经按 `workspace_id` 隔离。多租户基础已有。
3. **审计日志模型已建**：`AuditLog` model + `audit_repo` 已经有 `safe_create()` 和 `safe_list_for_resource()`。
4. **通知系统可扩展**：`NotificationConfig` 有 `channel` 字段（目前 webhook），加新 channel 只需扩展 enum + 实现发送方法。

#### 成功 Open-Core 公司怎么做的

| 公司 | 开源部分 | 付费部分 | 分离方式 |
|------|---------|---------|---------|
| **GitLab** | 核心 Git + CI/CD | RBAC, SSO, 合规, 高级 CI | 同一代码库，Ruby feature flag（`licensed_feature?(:feature_name)`）|
| **Sentry** | 错误追踪核心 | 团队管理、高级过滤、集成 | BSL license + 功能模块化 |
| **PostHog** | 产品分析核心 | 团队协作、高级分析、A/B testing | MIT 开源 + 付费 cloud features |
| **Metabase** | BI 查询 + 可视化 | SSO, 审计, 白标, 沙盒 | AGPL + 商业 license |

**共同模式**：
1. **单用户免费，团队/协作付费** — 这是最清晰的边界
2. **核心功能开源，企业合规/安全付费** — SSO、审计、RBAC
3. **同一代码库，feature flag 控制** — 不维护两个 repo
4. **Cloud/SaaS 版本有额外功能** — 降低自部署版的竞争力

#### 推荐实现方式

```python
# backend/app/core/edition.py（新建）
from enum import Enum
from app.config import settings

class Edition(str, Enum):
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"

def get_edition() -> Edition:
    """从环境变量或 license 文件读取当前版本"""
    return Edition(settings.BIOINFOFLOW_EDITION or "community")

def require_edition(minimum: Edition):
    """装饰器：限制 endpoint 的最低版本要求"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if get_edition().value < minimum.value:
                raise HTTPException(402, "This feature requires Pro edition")
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

**分离难度评估：低到中等。** 你不需要拆分代码库。用一个 `BIOINFOFLOW_EDITION` 环境变量 + edition check 装饰器就够了。这是 GitLab 验证过的模式。

### 定价建议

| 维度 | 参考 | 建议 |
|------|------|------|
| **定价锚点** | Seqera Tower Pro: ~$50/user/month; Terra: 按计算量; DNAnexus: $0.05-0.30/GB | Bioinfoflow Pro: **$49/user/month** |
| **免费层** | 1 user, 基础功能 | Community: 永久免费，单用户，所有核心功能 |
| **Pro 层** | 团队功能 + 高级调度 | $49/user/month（年付 $39）|
| **Enterprise** | SSO + 合规 + 支持 | 联系销售（预计 $500+/user/month）|
| **学术折扣** | 常见做法 | 学术机构 **50% off** |

**定价原则**：
1. **不要按计算量收费** — 你的价值是 "让 pipeline 管理更简单"，不是 "提供计算资源"
2. **按 seat 收费** — 简单、可预测、容易升级
3. **学术折扣必须有** — 生信市场学术占比大，折扣是 distribution 工具
4. **年付折扣 20%** — 降低 churn，提高 LTV

---

## 九、社交媒体获客策略

### 目标受众画像

| 受众 | 痛点 | 在哪里 | 内容偏好 |
|------|------|--------|---------|
| **生信工程师/分析师** | Pipeline 配置复杂、debug 痛苦 | Twitter/X, Biostars, nf-core Slack | 技术 demo, 代码片段 |
| **PI / 实验室负责人** | 不懂 CLI、需要结果不需要过程 | LinkedIn, 学术会议 | ROI 故事、时间节省数据 |
| **临床基因组学团队** | 合规要求、数据主权 | LinkedIn, 行业会议 | 安全、合规、on-premise |
| **CS/Bioinfo 学生** | 学习曲线陡、缺少好工具 | Twitter/X, Reddit r/bioinformatics | 教程、入门指南 |

### 内容策略：三种内容类型

#### Type 1：痛点共鸣帖（高传播）
**目的**：让目标受众觉得 "这个人懂我"

**Twitter/X 模板**：
```
生信分析的日常：

花 2 小时写 pipeline config
花 30 分钟跑分析
花 3 小时 debug "Process terminated with an error exit status (1)"

最后发现是 samplesheet 少了一个逗号。

每次都想——为什么没有 AI 帮我检查这些？

#bioinformatics #nextflow
```

```
你有没有过这种经历——

周五下午 5 点提交了一个 WGS 分析
周一早上回来发现第 2 个小时就报错了
整个周末白跑

如果有工具在报错的瞬间 Telegram 通知你
你周五晚上就能修好重新跑

这就是我在做的东西。
```

```
一个 nf-core/rnaseq 的 nextflow.config 有多少个参数？

我数了一下：47 个必填 + 89 个可选

没有人第一次能全部配对。

所以我做了一个 AI 助手——
你告诉它 "我有 12 个 human RNA-seq PE150 样本"
它帮你生成完整的 config + samplesheet

30 秒搞定。
```

#### Type 2：技术演示帖（高转化）
**目的**：展示产品能力，让人想试

**格式**：30-60 秒 GIF/视频 + 简短文案

**Twitter/X 模板**：
```
用 Bioinfoflow 在 RTX 4080 Super 上跑 30x WGS：

⏱️ 全流程 28 分钟（BWA-MEM2 + HaplotypeCaller via Parabricks）
💰 成本：$0（你自己的 GPU）
☁️ 同样的分析在 AWS 上要 $15-30/sample

[附 30 秒 demo 视频]

不需要 A100，不需要 cloud。
消费级 GPU + Bioinfoflow = 个人基因组学工作站。

#genomics #parabricks #nvidia
```

```
刚刚用 AI 帮一个博士生配置了 nf-core/sarek

他之前花了 3 天 debug 参数
AI 花了 45 秒生成正确配置
还顺便发现他的 samplesheet 有 2 个格式错误

[附 GIF: AI 对话 → 自动生成配置 → 一键提交运行]

这就是 Bioinfoflow 的 AI 助手。
```

#### Type 3：知识分享帖（建立权威）
**目的**：展示 domain expertise，建立信任

**Twitter/X 模板**：
```
Nextflow vs WDL：2026 年该选哪个？

一个 thread 🧵

我两个都用了 X 年，做了一个同时支持两者的平台。
这是我的诚实比较：

1/ Nextflow 的优势：nf-core 生态、channel 操作符、社区活跃
2/ WDL 的优势：语法清晰、Terra/Cromwell 支持、适合临床
3/ 选择建议：学术 → Nextflow，临床/大厂 → WDL
4/ 我的观点：你不应该被锁定在一个引擎上...

#bioinformatics #nextflow #wdl
```

```
为什么你的生信分析不应该在 cloud 上跑（大部分情况下）

thread 🧵

1/ 数据传输成本被忽视：100GB fastq 上传 = 等待 + egress 费用
2/ 数据主权：GDPR, HIPAA 对数据出境有严格要求
3/ 实际成本：一台 RTX 4080 的服务器 2 个月回本
4/ 什么时候该用 cloud：突发大量需求、没有 IT 团队、需要弹性
5/ 最佳方案：本地优先 + cloud burst（这也是 Bioinfoflow 的设计理念）
```

### 发布节奏

| 平台 | 频率 | 内容比例 |
|------|------|---------|
| **Twitter/X** | 每天 1-2 条 | 40% 痛点共鸣 + 30% 技术演示 + 30% 知识分享 |
| **LinkedIn** | 每周 2-3 条 | 60% 知识分享 + 30% 行业洞察 + 10% 产品更新 |
| **Reddit r/bioinformatics** | 每周 1 条 | 100% 有价值的内容（不要直接推销）|
| **nf-core Slack** | 需要时 | 帮人解决问题 → 顺带提你的工具 |
| **Biostars** | 每周回答 2-3 个问题 | 建立专家形象 |

### 关键原则

1. **80% 价值 / 20% 推广** — 大部分内容应该是有价值的知识，不是广告
2. **用中英双语** — 中文生信社区也很大（WeChat 公众号、知乎）
3. **截图/视频优先** — 文字不如图片，图片不如视频
4. **个人品牌 = 产品品牌** — Solo founder 阶段，你就是品牌。分享你的思考过程、踩过的坑、学到的东西
5. **回复每一条评论** — 早期每个互动都珍贵
