# Installer Experience Design

## Goal

Keep the one-line installer on the latest stable numeric release while making
its output concise and allowing users to select free frontend and backend ports
without rebuilding images.

## Principles

- Stable means immutable: the release installer keeps using its embedded
  numeric version and matching numeric image tags.
- Do not mutate unrelated host state: the installer reports port owners but
  never stops or kills them.
- Prefer one runtime configuration seam over a proxy, per-port image builds, or
  automatic port allocation.
- Hide successful transport noise while retaining bounded diagnostics on
  failure.

## Runtime API Configuration

The browser must know the host-visible backend port. `NEXT_PUBLIC_*` variables
are compiled into Next.js bundles, so they cannot solve this at container
startup. The frontend will expose a small `/runtime-config.js` route generated
from `BIOINFOFLOW_PUBLIC_API_BASE_URL`. The root layout loads it before
interactive application code, and the request runtime reads the resulting
`window.__BIOINFOFLOW_RUNTIME_CONFIG__.apiBaseUrl` on the client. Server-side
code falls back to the runtime environment and then the existing compiled
default.

This preserves direct browser-to-backend HTTP, SSE, and WebSocket connections.
It avoids a reverse proxy and therefore adds no extra data path or WebSocket
upgrade implementation.

The localhost Compose file will:

- publish `127.0.0.1:${BACKEND_PORT:-8000}:8000`;
- publish `127.0.0.1:${FRONTEND_PORT:-3000}:3000`;
- pass `BIOINFOFLOW_PUBLIC_API_BASE_URL=http://localhost:${BACKEND_PORT:-8000}/api/v1`
  to the frontend;
- continue configuring backend CORS from the selected frontend port.

## Installer Behavior

`FRONTEND_PORT` and `BACKEND_PORT` default to `3000` and `8000`. Both must be
decimal integers from 1 through 65535 and must differ. Selected values are
persisted in the managed `.env` file so repair, update, uninstall, and purge use
the same configuration.

Before a fresh installation, the installer checks both selected ports. When a
port is occupied it prints the bounded `lsof` listener record, identifies
whether the frontend or backend port failed, and suggests a retry with explicit
environment variables. It never signals the owning process.

Successful installation output is organized into stable stages:

1. Docker readiness.
2. Stable release and architecture selection.
3. Release asset download and checksum verification.
4. Image download.
5. Service startup and health checks.
6. Final frontend and backend URLs.

Internal release downloads use silent curl flags. Successful Compose pull and
startup output is suppressed; existing bounded status and log diagnostics are
shown on failure.

## Release Contract

The default release path remains unchanged: a packaged installer embeds a bare
numeric version and pulls images with that exact tag. No `main`, `edge`, or
floating development channel is added.

The release workflow smoke test will install with non-default frontend and
backend ports on both amd64 and arm64. It will verify the generated environment,
backend health, frontend health, uninstall, and purge. This proves that one
published frontend image supports runtime-selected backend ports.

## Testing

- Installer harness tests validate port ranges, distinct ports, persisted
  values, bounded owner diagnostics, stable-release messaging, silent curl
  flags, and stage output.
- Frontend unit tests validate runtime configuration serialization and API and
  WebSocket URL resolution.
- Docker Compose rendering tests validate both custom port mappings and the
  runtime frontend API URL.
- Release workflow contract tests require non-default ports in both architecture
  smoke jobs.
- Full shell, frontend lint/test/build, Compose, actionlint, and diff checks run
  before publication.

## Non-Goals

- No process termination.
- No automatic port scanning or selection.
- No development-image installer channel.
- No reverse proxy.
- No custom short domain.
