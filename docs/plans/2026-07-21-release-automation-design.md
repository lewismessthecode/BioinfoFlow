# Release Automation Design

**Date:** 2026-07-21

## Goal

Establish `0.1.0` as Bioinfoflow's first formally tracked release and automate
future curated releases without publishing on every merge to `main`.

All version tags, changelog entries, GitHub Release notes, workflow copy, and
release documentation must be written in English. Git tags use bare semantic
versions such as `0.1.0`; they never use a `v` prefix.

## Release Model

Bioinfoflow follows a curated, Cursor-style release cadence:

1. Feature and fix pull requests continue to merge into `main`.
2. Release Please maintains one release pull request containing the proposed
   version and changelog changes.
3. The release pull request may accumulate changes for one or two weeks, or
   until a product milestone is ready.
4. Merging the release pull request is the only normal action that creates a
   formal release.
5. The resulting GitHub Release publishes immutable versioned container images.

Merging an ordinary pull request is development activity, not a formal release.

## Version Policy

Bioinfoflow uses one version for the backend, frontend, Git tag, GitHub Release,
and paired container images.

- `fix:` and `perf:` changes produce a patch candidate.
- `feat:` changes produce a minor candidate.
- Breaking changes produce a minor candidate while Bioinfoflow remains below
  `1.0.0`.
- `docs:`, `refactor:`, `test:`, `chore:`, and `ci:` do not create a release by
  themselves.
- `1.0.0` will be an explicit project decision rather than an automatic result
  of pre-1.0 development.

The squash-merged pull request title is the canonical Conventional Commit used
for version calculation.

## Changelog Policy

`CHANGELOG.md` is a user-facing product record, not a list of every merged pull
request.

Automatic sections include:

- Features
- Bug Fixes
- Performance Improvements
- Breaking Changes, when applicable

Tests, CI maintenance, routine dependency updates, planning documents, internal
refactors, and other user-invisible work are omitted by default. Maintainers may
edit the release pull request before merging when an otherwise omitted change is
important to users.

The initial `0.1.0` entry consolidates earlier development into approximately
10 to 15 curated highlights. It does not enumerate the repository's historical
pull requests.

## Automation Components

### Release Please

A GitHub Actions workflow runs on pushes to `main` and manual dispatch. It uses
the manifest configuration and `include-v-in-tag: false` to maintain a release
pull request and create bare numeric tags.

The release configuration keeps the application version synchronized across
the backend package and lock metadata, backend runtime default, frontend
package metadata, and generated API contract where applicable. Tests must
compare against the canonical application version instead of requiring manual
edits for every release.

### Container Publishing

Development and formal-release image channels are separated:

- A merge to `main` may publish `main` and `sha-<12-char-sha>`.
- A formal release publishes immutable `<major>.<minor>.<patch>` tags.
- A formal release also advances `<major>.<minor>`, `<major>`, and `latest`.
- `latest` means the latest formal release and is not updated by ordinary
  merges to `main`.

Backend and frontend images share the same application version. A formal
release publishes both images so the version always identifies a complete,
deployable Bioinfoflow pair.

### Bootstrap Release

The first release is intentionally special:

1. Merge the release-automation pull request containing the initial changelog,
   configuration, workflows, and documentation.
2. Create the `0.1.0` GitHub Release from that merge commit.
3. Publish the paired `0.1.0` container images through the release event.
4. Future releases use the normal Release Please pull-request flow.

The bootstrap commit contains the current application code plus release
infrastructure; it introduces no unrelated product feature.

## Maintainer Guidance

`AGENTS.md` and `CLAUDE.md` contain only the durable rules agents need while
preparing pull requests: numeric tags, Conventional Commit version effects, the
release pull-request gate, and a link to the detailed SOP. The full procedure
lives in `docs/development/releases.md` to avoid duplicating operational detail.

The SOP covers:

- interpreting the proposed version;
- reviewing and optionally editing the changelog;
- waiting for required checks;
- merging the release pull request;
- verifying the tag, GitHub Release, and container images;
- publishing urgent patch releases;
- handling a failed release workflow without moving or overwriting an immutable
  version tag.

## Failure Handling

- Release jobs must be idempotent where GitHub and GHCR permit it.
- Exact version tags are immutable and are never silently overwritten.
- A failed container build leaves the GitHub Release visible but incomplete;
  the workflow is rerun for the same release rather than creating a new version.
- A malformed Conventional Commit title is corrected before squash merge so it
  cannot silently produce the wrong version.
- The release pull request is never auto-merged.
- Formal release workflows use concurrency controls to prevent two releases
  from publishing overlapping tags simultaneously.

## Verification

Implementation verification includes:

- syntax validation for all GitHub Actions workflows;
- automated assertions for Release Please configuration and numeric tags;
- automated assertions that ordinary `main` builds do not publish `latest`;
- automated assertions for formal version, alias, and `latest` image tags;
- backend version consistency tests;
- frontend metadata consistency checks;
- `git diff --check` and the repository's relevant backend and frontend checks.

## Out of Scope

- Alpha, beta, canary, or nightly release channels.
- Automatic daily releases.
- Independent backend and frontend versions.
- Retrospective changelog entries for every historical pull request.
- Automatically declaring `1.0.0`.
