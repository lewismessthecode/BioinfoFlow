# GitHub CI/CD

Bioinfoflow uses GitHub Actions to move isolated worktree branches through pull
requests, one required CI gate, intentional release approval, and immutable-tag
publication.

## Workflow Map

- `CI` validates pull requests, merge-queue groups, pushes to `main`, and manual
  runs.
- `CodeQL` performs Python and JavaScript/TypeScript security analysis.
- `Publish Images` is a reusable formal-release workflow that builds all three
  GHCR images from one numeric tag.
- `Release Please` maintains the version/changelog pull request and creates the
  numeric tag and GitHub Release after that PR is intentionally merged.
- `Publish Release` consumes the numeric tag, publishes three formal images,
  verifies multi-architecture manifests, smoke-tests the localhost installer,
  and uploads installer assets.

There is no custom auto-merge workflow. Use GitHub's native auto-merge so the
developer chooses squash or rebase explicitly.

## Pull-request CI

Branch protection requires one check named `CI`. The final gate always runs and
fails closed. Internal work is selected by changed area:

- `backend checks`: backend lint and tests;
- `frontend lint`, `frontend test`, and `frontend build`;
- `docker build`: backend and frontend image builds;
- `installer checks`: installer shell tests and localhost Compose rendering;
- `workflow checks`: Actionlint over every workflow.

Do not add workflow-level path filters to `CI`. A completely skipped required
workflow can remain Pending forever. Docs-only changes instead skip the leaf
jobs and receive a successful final gate.

Pushes to `main` and manual CI runs execute the complete path. The workflow also
listens to `merge_group`, so it is ready if the repository later moves from
strict branch protection to GitHub's merge queue.

## Release Please credential

`Release Please` requires the `RELEASE_PLEASE_TOKEN` repository secret. Use a
GitHub App installation token or fine-grained PAT with the minimum repository
permissions needed to write contents, pull requests, and issues.

Do not fall back to `GITHUB_TOKEN`. Pull requests created or updated by the
workflow's own `GITHUB_TOKEN` do not naturally produce usable required PR
checks. Do not compensate by manually dispatching another CI run; that run is
not the pull request's normal `pull_request` check.

Release PRs remain an intentional production gate and must not be auto-merged.

## Worktrees and parallel agents

Use this ownership rule for Codex, Claude Code, and human contributors:

```text
one feature = one writing owner = one worktree = one branch = one pull request
```

Start from the latest remote default branch:

```bash
git fetch origin --prune
git worktree add ../bioinfoflow-feature -b feature/example origin/main
cd ../bioinfoflow-feature
```

Before editing, confirm the branch and worktree topology:

```bash
git branch --show-current
git worktree list
```

Parallel read-only exploration is safe. Parallel writers must have disjoint file
ownership. Assign one integration owner for conflict-prone files such as GitHub
workflows, changelogs, dependency locks, database migrations, and locale files.

Before opening or updating a PR:

```bash
git fetch origin --prune
git rebase origin/main
git push --force-with-lease
```

Create the PR explicitly with a Conventional Commits title. For native rebase
auto-merge:

```bash
gh pr merge --rebase --auto --delete-branch <PR-URL>
```

The normal repository policy remains squash merge because the PR title is the
release unit. Use rebase merge when preserving the branch's individual commits
is intentional.

## Branch protection

`scripts/github/configure-repo.sh` configures:

- required check `CI` in strict mode;
- linear history;
- resolved review conversations;
- no force pushes or branch deletion;
- read-only default workflow permissions;
- GitHub native auto-merge and branch deletion after merge.

Strict mode means a PR must be validated against current `main`. If parallel PR
volume makes repeated rebases expensive, migrate the repository to a merge-queue
ruleset in one atomic change. Keep `merge_group` enabled in required workflows
before enabling that queue.

## Development builds

Ordinary `main` pushes do not publish GHCR images. Source development uses the
repository Compose stack, while published packages remain intentional release
artifacts. This avoids mutable `main` image ordering races and unnecessary
multi-architecture builds when no deployment consumes that channel.

## Formal releases

Merging the Release Please PR creates a bare numeric tag such as `0.3.0` and a
GitHub Release. The same workflow then directly calls `Publish Release` through
`workflow_call`; it does not dispatch a detached follow-up run.

`Publish Release` validates and checks out the numeric tag before producing:

```text
0.3.0
0.3
0
latest
```

All three images, installer assets, checksums, manifest verification, and
amd64/arm64 smoke tests consume that tag. Manual recovery supplies the same
numeric tag and may be started from any workflow ref because the input tag, not
the launcher ref, is the source of truth.

See [Release Maintainer SOP](releases.md) for release and recovery procedures.
