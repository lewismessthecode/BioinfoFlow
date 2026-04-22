# Deploy Script Multi-Architecture & GHCR Release Design

## Goal
Add explicit architecture-aware image builds for offline deployment from a Mac host, and add a release workflow that publishes multi-architecture images to GHCR.

## Scope
- Update `deploy.sh` to support `--arch amd64|arm64` for `build`, `push`, and `sync`.
- Add `release` command to publish `linux/amd64` and `linux/arm64` images to GHCR in one step.
- Expand built-in help output with detailed usage and GHCR setup instructions.
- Update `README.md` deployment documentation to match the script.

## Constraints
- Keep the existing offline deployment flow (`save` -> `scp` -> `load` -> `compose up`) intact.
- Do not require source code on the server.
- Default single-architecture deploy target should be `amd64`.
- `release` should always build and push both `amd64` and `arm64` variants.

## Command Design
### build
`./deploy.sh build [--arch amd64|arm64]`

Build backend and frontend images for a single target platform using Docker Buildx and load them into the local Docker image store.

### push
`GHCR_USER=<user> ./deploy.sh push [--arch amd64|arm64]`

Build a single-architecture pair of images and push them to GHCR with architecture-specific tags.

### sync
`./deploy.sh sync [--arch amd64|arm64] user@server [remote_dir]`

Build a single-architecture pair of images, save them to a tarball, transfer them to the target server, load them there, and start the services.

### release
`GHCR_USER=<user> IMAGE_TAG=<tag> ./deploy.sh release`

Build and push a multi-architecture manifest for backend and frontend to GHCR covering `linux/amd64` and `linux/arm64`.

## Tagging Rules
- Local/offline images keep the existing names:
  - `bioinfoflow-backend:<tag>`
  - `bioinfoflow-frontend:<tag>`
- Single-architecture GHCR pushes add an architecture suffix:
  - `ghcr.io/<user>/bioinfoflow-backend:<tag>-amd64`
  - `ghcr.io/<user>/bioinfoflow-backend:<tag>-arm64`
  - same for frontend
- Multi-architecture release publishes canonical tags without suffix:
  - `ghcr.io/<user>/bioinfoflow-backend:<tag>`
  - `ghcr.io/<user>/bioinfoflow-frontend:<tag>`

## Build Strategy
- Replace `docker compose build` with explicit `docker buildx build` calls.
- Backend build uses `backend/Dockerfile` and backend context.
- Frontend build uses `frontend/Dockerfile`, frontend context, and preserves current build args from `docker-compose.yml`.
- Single-architecture builds use `--load` so `docker save` and local testing keep working.
- Multi-architecture release uses `--push` because multi-platform manifests cannot be loaded into the local image store.

## GHCR Setup Guidance
The script help text should include:
- required token scopes (`write:packages`, `read:packages`, optional `delete:packages`)
- local login command using `docker login ghcr.io`
- note that private images require server-side login for pull-based deployments
- recommendation to use explicit `GHCR_USER` instead of relying on local git config
- recommendation to use versioned `IMAGE_TAG` values instead of only `latest`

## Validation Rules
- Reject unsupported `--arch` values.
- Require `GHCR_USER` for `push` and `release`.
- Require Docker Buildx for all build-related commands.
- `release` must not accept `--arch`; it always targets both platforms.

## Testing
- Add a lightweight regression test script that stubs `docker`, `ssh`, `scp`, and `git` to verify command construction.
- Verify:
  - `build --arch amd64` uses `docker buildx build --platform linux/amd64 ... --load`
  - `build --arch arm64` uses `linux/arm64`
  - `release` uses both platforms and `--push`
  - help output mentions `--arch`, `release`, and GHCR setup

## Risks
- Cross-platform frontend dependencies (e.g. native modules) depend on Docker build correctness rather than local host architecture. Buildx addresses this by targeting the requested platform explicitly.
- Multi-architecture release can be slower than single-platform builds. This is acceptable because it is a release workflow, not the default dev loop.

## Success Criteria
- Offline deploy from a Mac to an amd64 Linux server succeeds with `./deploy.sh sync --arch amd64 ...`.
- Offline deploy from a Mac to an arm64 Linux server succeeds with `./deploy.sh sync --arch arm64 ...`.
- GHCR release can publish a single tag that works on both amd64 and arm64 servers.
- Help output is detailed enough that future setup steps are self-contained.
