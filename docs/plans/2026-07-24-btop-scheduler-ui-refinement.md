# btop packaging and scheduler UI refinement

## Goal

Make the scheduler's system monitor available in release/Compose installs and
make the scheduler status page easier to scan without changing its data flow or
route ownership.

## Root cause

The `/scheduler/btop/ws` endpoint spawns `btop` from the backend process. Under
Docker Compose and `install.sh`, that process runs inside the published backend
container. The backend image installs `procps` but not `btop`, so a host-level
`btop` installation cannot satisfy the container lookup.

## Changes

1. Add `btop` to the backend image's system packages.
2. Add a Dockerfile packaging test so release images cannot silently drop it.
3. Refine the scheduler state strip around one operational conclusion, six
   supporting metrics, and a separate last-updated line.
4. Rename the vague advanced-view action to an explicit monitor action.
5. Remove the progress-like bar from active runs and label the displayed value
   as an estimated CPU share.
6. Stop the active-runs panel from stretching into unused vertical space.
7. Update English and Chinese copy and the scheduler integration test.
8. Align the live-capacity and active-runs area with the Dashboard flat-section
   pattern: one shared surface, a single divider, compact header actions, and a
   left-aligned empty state without nested dashed cards.

## Verification

- `rtk uv run pytest tests/test_dockerfile_packaging.py tests/test_services/test_btop_service.py tests/test_api/test_scheduler_btop.py`
- `rtk uv run ruff check app/services/btop_service.py tests/test_dockerfile_packaging.py tests/test_services/test_btop_service.py tests/test_api/test_scheduler_btop.py`
- `rtk bun run test -- frontend/tests/integration/pages/scheduler-page.test.tsx`
- `rtk bun run lint`
- `rtk bun run lint:i18n`
- `rtk git diff --check`

If Docker is available, also build the backend image and verify
`command -v btop` inside it.
