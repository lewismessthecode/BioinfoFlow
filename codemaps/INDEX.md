# Codemaps Index

**Last Updated:** 2026-07-11

These maps summarize the current source tree. They are contributor orientation,
not a replacement for the user-facing documentation or generated API schema.

## Areas

- [Architecture](architecture.md): system boundaries and runtime flows.
- [Backend](backend.md): FastAPI routers, services, repositories, workflow engines, scheduler, AgentCore, and CLI.
- [Frontend](frontend.md): Next.js routes, shared UI, AgentCore workbench, auth, and client data flow.
- [Data](data.md): current ORM domains, repositories, schemas, migrations, and frontend contracts.
- [Dependencies](dependencies.md): declared runtime packages and external systems.

## Canonical References

- Setup and operations: [`README.md`](../README.md), [`RUNBOOK.md`](../RUNBOOK.md), and [Docker Quick Start](../docs/getting-started/docker.md).
- Public architecture: [Architecture](../docs/architecture.md) and [Architecture Reference](../docs/reference/architecture.md).
- Exact API surface: the FastAPI OpenAPI document at `/api/v1/openapi.json` on a running backend.
- Exact CLI surface: `uv run bif --help` and command-specific help from `backend/`.

Refresh these maps after major source-tree changes. If a map conflicts with
current code, the implementation and tests win.
