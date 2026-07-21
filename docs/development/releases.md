# Release Maintainer SOP

Bioinfoflow uses a curated release cadence. Ordinary pull requests continue to
merge into `main`, while Release Please maintains a separate release pull
request. A formal release happens only when a maintainer intentionally merges
that release pull request.

All version tags are bare numeric semantic versions such as `0.1.0`. Do not add
a `v` prefix.

## Release Channels

| Channel | Example | Meaning |
| --- | --- | --- |
| Exact release | `0.2.1` | Immutable release built from the matching Git tag |
| Minor alias | `0.2` | Latest formal release in the `0.2.x` line |
| Major alias | `0` | Latest formal pre-1.0 release |
| Stable | `latest` | Latest formal release |
| Development | `main` | Latest eligible build from `main` |
| Development SHA | `sha-abc123def456` | Build associated with one exact commit |

The `main` and SHA channels are for development and diagnosis. Use an exact
numeric version in deployments that must be reproducible.

## Daily Pull Request Rules

The squash-merged pull request title controls the next version and changelog:

| Pull request title | Version effect | Public changelog |
| --- | --- | --- |
| `fix: ...` | Patch | Bug Fixes |
| `perf: ...` | Patch | Performance Improvements |
| `feat: ...` | Minor | Features |
| `feat!: ...` or another breaking `!` title | Minor while below `1.0.0` | Breaking change |
| `docs:`, `refactor:`, `test:`, `chore:`, `ci:` | No release by itself | Hidden by default |

Normalize the pull request title before squash merge. Do not edit
`CHANGELOG.md` in an ordinary feature or fix pull request; Release Please owns
the next release entry.

## Normal Release Procedure

1. Open the Release Please pull request whose title looks like
   `chore(main): release bioinfoflow 0.2.0`.
2. Confirm that the proposed version matches the merged work:
   - fixes and performance work only: patch;
   - at least one feature: minor;
   - breaking pre-1.0 work: minor with a clearly written breaking-change note.
3. Review `CHANGELOG.md` from a user's perspective. Remove internal detail and
   improve unclear wording. Make manual changelog edits only after the release
   contents are stable because later merges to `main` may update the Release PR.
4. Confirm that backend, frontend, and Docker required checks pass.
   Release Please dispatches the CI workflow directly for its generated branch,
   so these checks run even though the pull request was created by
   `GITHUB_TOKEN`.
5. Do not add the `automerge` label. Merge the Release PR intentionally when the
   release is ready.
6. The `Release` workflow creates the numeric Git tag and GitHub Release, then
   dispatches `Installer Release` for the backend, authenticated frontend, and
   localhost frontend multi-architecture images. That workflow smoke-tests the
   localhost installer and attaches `install.sh`, `docker-compose.local.yml`,
   and `SHA256SUMS` to the same GitHub Release.
7. Verify the release:

   ```bash
   rtk gh release view 0.2.0
   rtk gh run list --workflow release-please.yml --limit 5
   rtk gh run list --workflow release.yml --limit 5
   rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-backend:0.2.0
   rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-frontend:0.2.0
   rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-frontend-localhost:0.2.0
   ```

8. For a deployment, pin both images to the same exact version:

   ```env
   IMAGE_REGISTRY=ghcr.io/lewismessthecode
   IMAGE_TAG=0.2.0
   ```

## One-Time `0.1.0` Bootstrap

After the release-automation pull request is merged, create the first Release
from that merge commit. Run from the checkout that owns `main` (normally the
original checkout, not a detached linked worktree) after synchronizing it with
`origin/main`:

```bash
rtk git fetch origin --prune --tags
rtk git switch main
rtk git pull --ff-only origin main
rtk gh release create 0.1.0 \
  --target "$(rtk git rev-parse origin/main)" \
  --title "0.1.0" \
  --notes-file CHANGELOG.md
rtk gh workflow run release-please.yml -f publish_version=0.1.0
```

The manual workflow input validates that `0.1.0` is a numeric version and that
the matching GitHub Release and Git tag already exist. It then dispatches the
same installer, asset, and formal image workflow used by future automatic releases.

Verify the bootstrap with:

```bash
rtk gh release view 0.1.0
rtk gh run list --workflow release-please.yml --limit 5
rtk gh run list --workflow release.yml --limit 5
rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-backend:0.1.0
rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-frontend:0.1.0
rtk docker buildx imagetools inspect ghcr.io/lewismessthecode/bioinfoflow-frontend-localhost:0.1.0
```

## Urgent Patch Release

1. Prepare and merge a narrowly scoped `fix:` pull request.
2. Wait for Release Please to update or create the release pull request.
3. Confirm that the proposed version is the next patch version.
4. Review the Bug Fixes entry and required checks.
5. Merge the Release PR intentionally.
6. Verify the GitHub Release and both exact-version images.

Do not bypass the Release PR by manually moving an existing tag.

## Failed Release Recovery

- If the Release workflow fails before creating the GitHub Release, fix the
  workflow or permissions and rerun the failed job.
- If the GitHub Release exists but an image job fails, rerun the same workflow
  from the same immutable Git tag. Rebuilding the same tag is recovery; never
  point the version at a different commit.
- Do not delete and recreate a released version merely to change release notes.
  Edit the GitHub Release text and correct `CHANGELOG.md` in a follow-up pull
  request when needed.
- Do not manually overwrite an exact numeric image tag with a build from another
  commit.
- Mutable aliases (`0.2`, `0`, and `latest`) advance only when a newer formal
  release succeeds.

## When to Release

Release when one of these conditions is met:

- a coherent set of user-facing changes is ready;
- the Release PR has accumulated roughly one or two weeks of useful work;
- a deployment needs a reproducible rollback point;
- an urgent user-facing fix is ready;
- a large refactor is about to begin and the current stable state should be
  preserved.

Do not release merely because another ordinary pull request was merged.
