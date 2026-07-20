# Changelog

All notable user-facing changes to Bioinfoflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
while it remains under active pre-1.0 development.

## [0.1.0] - 2026-07-21

This is the first formally tracked release of Bioinfoflow. Earlier development
history has been consolidated into this release instead of being listed pull
request by pull request.

### Highlights

- Added a local-first workspace for managing bioinformatics projects, files,
  workflow bindings, run history, and outputs.
- Added workflow registration and execution through shared Nextflow and
  WDL/MiniWDL adapters.
- Added persistent scheduling with concurrency controls, resource accounting,
  retries, timeouts, cleanup, and restart recovery.
- Added inspectable run DAGs, logs, events, inputs, audit trails, and collected
  results.
- Added an Agent that can inspect platform state, call tools, prepare work, and
  submit approved operations.
- Added explicit permission and approval boundaries for consequential Agent
  actions.
- Added managed local projects, existing-directory projects, and SSH-backed
  remote projects.
- Added saved remote connections, connection probes, remote terminals, and
  bounded remote Agent tools.
- Added configurable hosted and OpenAI-compatible model providers.
- Added the Next.js web interface for projects, workflows, runs, images,
  connections, scheduling, settings, terminals, and Agent sessions.
- Added the HTTP-only `bif` command-line client for automation and operational
  access.
- Added Docker Compose deployment, GHCR container publishing, CI, CodeQL, and
  pull request automation.

[0.1.0]: https://github.com/lewismessthecode/BioinfoFlow/releases/tag/0.1.0
