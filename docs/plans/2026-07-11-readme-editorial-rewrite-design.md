# README Editorial Rewrite Design

**Goal:** Rewrite the English and Chinese root READMEs so a first-time open-source visitor can quickly understand Bioinfoflow, see why it is worth trying, and start it without reading a deployment manual.

## Audience

The primary reader is an open-source developer encountering Bioinfoflow for the first time. The README must help that reader answer, within roughly one minute:

1. What is Bioinfoflow?
2. What is distinctive about it?
3. Can I run it locally without a large commitment?

Operators and contributors remain secondary audiences. Detailed deployment, configuration, and troubleshooting material should link to canonical documentation instead of dominating the root README.

## Editorial Direction

Use a technical-editorial narrative: precise, restrained, and opinionated enough to be memorable. The README should read like a carefully edited open-source project introduction rather than a feature inventory or product landing page.

The voice should be confident without promotional exaggeration. Claims must remain grounded in the current implementation. Prefer concrete nouns and verbs over category labels and slogans.

## Product Positioning

Describe Bioinfoflow as an Agent-guided workspace and runtime for bioinformatics analysis. Its defining quality is that the Agent shares real project, run, tool, and remote-host context with the rest of the platform and can act within explicit permission and approval boundaries.

Local-first operation remains an important deployment principle, but not the headline identity. Bioinfoflow can work with managed local data, external local directories, and SSH-backed remote projects while keeping the platform under the user's control.

Nextflow, WDL, and MiniWDL are supported execution engines, not the headline identity of the product. Mention them where implementation compatibility matters, but do not define Bioinfoflow primarily through those engine names.

Use **Agent** consistently in public README prose. Do not use **AgentCore**. The README may describe what the Agent can do—inspect files, prepare configurations, operate approved tools, work with selected remote hosts, and submit runs—without exposing internal subsystem naming.

## Information Architecture

1. **Identity and proposition** — logo, project name, an Agent-forward subtitle, badges, and language switcher.
2. **Opening narrative** — two or three short paragraphs explaining the fragmented work Bioinfoflow brings together and the local-first boundary it preserves.
3. **Immediate trial path** — a compact clone/configure/start command near the top.
4. **Product preview** — retain the existing product GIF directly after the initial proposition.
5. **What comes together** — organize capabilities into four coherent domains rather than a long flat feature list:
   - projects, data, and reproducible run workspaces;
   - workflow execution, scheduling, logs, DAGs, and outputs;
   - the action-capable, approval-aware Agent and browser/CLI tools;
   - remote connections and infrastructure the user controls.
6. **Who it is for** — a short suitability section for individual researchers, bioinformatics developers, and small teams operating their own compute.
7. **Quick start** — the shortest source-build Docker path, essential prerequisites, login, and local URLs. Move exhaustive environment-variable and registry details to the Docker guide and runbook.
8. **How it works** — a compact architecture flow and explicit component boundaries. Workflow engines appear here as adapters behind the scheduler.
9. **CLI and development** — a few representative commands plus links to full references.
10. **Operational boundaries** — concise, candid notes about Docker socket access, local-first deployment assumptions, identity-mounted paths, and SSH not being a workflow dispatch backend.
11. **Documentation and license** — curated links rather than an exhaustive table of contents.

## English Voice

- Use idiomatic open-source technical English.
- Keep paragraphs short and sentences direct.
- Avoid inflated terms such as “revolutionary,” “seamless,” or “production-grade” unless the repository supplies an objective definition and proof.
- Avoid repeating “local-first,” “control plane,” and “Agentic” as slogans.
- Prefer explanations of what the system does and where it runs.

## Chinese Voice

The Chinese README is an independently written counterpart, not a line-by-line translation.

- Use natural, composed written Chinese with varied sentence rhythm.
- Prefer established expressions such as “生物信息分析”“分析流程”“运行记录”“远程主机”“结果目录” and “本地部署”.
- Avoid unnecessary mixed-language phrases. Keep English only for proper names, commands, protocols, and technical terms whose translation would be less clear.
- Avoid internet-marketing language, fashionable abstractions, and mechanical structures copied from English.
- Preserve the same facts, section order, commands, caveats, and links as the English README even when the prose is reorganized.

## Detail Boundary

The README should be shorter and more readable than the current version while remaining technically useful. It should not enumerate every provider environment variable, private registry behavior, complete deployment matrix, or all development checks. Those details belong in `docs/getting-started/docker.md`, `RUNBOOK.md`, and the reference pages.

Keep enough detail to establish credibility: actual commands, supported operating model, component boundaries, and important limitations.

## Verification

- Compare all behavioral claims with current code and the completed documentation audit.
- Keep English and Chinese commands, links, features, and caveats aligned.
- Validate relative Markdown links and anchors.
- Run `rtk git diff --check`.
- Confirm no public README occurrence of `AgentCore` remains.
- Re-run relevant documentation/i18n checks and update the existing draft PR.
