# CI/CD Invariants Fix Plan

## Goal

Make pull-request validation deterministic and make every formal release artifact
come from the same immutable numeric tag.

## Invariants

- Creating a pull request must be an explicit client action; a workflow must not
  create another workflow-triggering event with `GITHUB_TOKEN`.
- A changed area passes only when every required child job reports `success`.
- Installer, Compose, bundled-skill, and workflow changes are validated before
  merge.
- Release verification, packaging, images, and uploaded assets all use the same
  immutable numeric tag.
- Release Please pull requests cannot be auto-merged.

## Implementation

1. Add repository-level contract tests for the invariants above and verify they
   fail against the current workflows.
2. Remove push-to-PR automation and its ineffective trusted-run approval chain;
   document explicit PR creation.
3. Make CI aggregators fail closed and add installer/workflow validation under
   the stable `docker` delivery gate.
4. Require tag-based release recovery, checkout that tag in every source-reading
   job, and exclude Release Please pull requests from auto-merge.

## Verification

- `rtk uv run pytest tests/scripts/test_release_automation.py`
- `rtk actionlint .github/workflows/*.yml`
- `rtk sh scripts/tests/install-test.sh`
- `rtk docker compose --env-file scripts/tests/fixtures/local.env -f docker-compose.local.yml config`
- `rtk git diff --check`
