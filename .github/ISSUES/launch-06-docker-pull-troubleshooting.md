---
title: "Add troubleshooting guide for Docker image pulls"
labels: ["docs", "docker", "good first issue"]
---

## Context

The first nf-core/rnaseq demo run may spend most of its time pulling images.
New users need quick help for common Docker registry, proxy, and disk-space
problems.

## Scope

- Add a troubleshooting section to the Docker quick start or runbook.
- Include commands for inspecting Docker disk usage and failed pulls.
- Link from the nf-core/rnaseq demo README.

## Acceptance Criteria

- [ ] Docs include `docker system df`, `docker pull`, and `docker compose logs` examples.
- [ ] Proxy/offline environments are called out as limitations.
- [ ] The canonical demo links to the troubleshooting section.
- [ ] The guide is written for a first-time user.
