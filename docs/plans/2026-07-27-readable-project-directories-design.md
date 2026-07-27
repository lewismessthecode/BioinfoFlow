# Readable Managed Project Directories Design

## Status

Approved direction for implementation on 2026-07-27.

## Problem

BioinfoFlow currently stores every managed project under
`<BIOINFOFLOW_HOME>/projects/<project UUID>`. The UUID is a sound database
identity, but it produces an unfriendly terminal and filesystem experience. A
project displayed as `Bioinfoflow Demo` still opens in a directory such as
`projects/37ec8480-5069-54e7-90ff-609952d0cfed`.

New managed projects should use stable, readable, cross-platform directory
names derived from the project display name. Existing projects must keep their
current UUID directories and must not be migrated.

## Decision

Add a nullable, immutable `directory_name` column to `projects` and use it as
the managed filesystem directory when present.

- New managed projects receive a persisted ASCII kebab-case directory name.
- Existing rows keep `directory_name = NULL` and continue using their UUID.
- External projects continue using `external_root_path`.
- Remote projects continue using `remote_root_path` and never receive a local
  managed directory name.
- Renaming a project changes only its display name. It does not rename or move
  the directory.

This matches the stable-workspace behavior expected from Codex: the readable
directory is chosen when the workspace is created, while later display-name or
task-title changes do not silently move files.

## Naming Rules

Introduce a focused helper that converts a display name into a safe base name.
Use `pypinyin` for Chinese transliteration, plus Unicode normalization for
accented Latin text, before applying the ASCII path rules.

Examples:

| Project name | Base directory name |
| --- | --- |
| `BioinfoFlow Demo` | `bioinfoflow-demo` |
| `测试` | `ce-shi` |
| `肿瘤 RNA 分析` | `zhong-liu-rna-fen-xi` |
| `  Demo___Project  ` | `demo-project` |

The helper must:

- lowercase Latin characters;
- transliterate Unicode text to ASCII;
- replace runs of spaces, punctuation, and separators with one `-`;
- remove leading and trailing separators;
- emit only `a-z`, `0-9`, and `-`;
- cap the base name at 100 characters without leaving a trailing `-`;
- fall back to `project` if no usable characters remain.

The final persisted value must pass the existing safe path-name rules.

## Uniqueness And Concurrency

Managed project directory names are globally unique because all managed
projects share one `projects/` filesystem root. The first project receives the
base name; later collisions receive the smallest available numeric suffix:

```text
ce-shi
ce-shi-2
ce-shi-3
```

Add a database unique constraint for non-null `directory_name` values. The
creation path must also treat an existing filesystem entry as occupied, even if
no database row currently references it. This prevents BioinfoFlow from
claiming a manually created directory or an orphan left by an interrupted
operation.

Directory reservation and database persistence must tolerate concurrent
requests. For each candidate, creation will:

1. reject any existing filesystem entry, including a dangling symbolic link;
2. add and flush the project row so the database uniqueness constraint reserves
   the name;
3. atomically create the candidate root with `exist_ok=False`;
4. create `data/` and `runs/`, then commit the transaction.

A directory-name uniqueness conflict rolls back and retries the next suffix. A
filesystem collision after the database flush also rolls back and retries. The
code must distinguish the directory-name constraint from unrelated integrity
errors. If layout creation or commit fails for a non-collision reason, it must
remove only the directory tree positively known to have been created by that
request; it must never remove a pre-existing path.

Suffixes count toward the maximum directory-name length, so a long base is
trimmed before appending `-2`, `-3`, and later values.

## Data Model And Migration

Create a new Alembic revision after `0055_merge_agent_heads`, the current merged
head. The migration adds:

```text
projects.directory_name VARCHAR(120) NULL
UNIQUE INDEX uq_projects_directory_name(directory_name)
```

No backfill runs. SQLite and PostgreSQL both allow multiple `NULL` values in a
unique index, so all legacy projects remain valid and retain UUID lookup.

The field is an internal storage identity and is not required in create or
update request payloads. API clients cannot select or mutate it. Existing API
responses remain compatible; filesystem paths returned or used internally are
resolved through the project model.

## Path Resolution

For a managed `Project` object, `project_home(project)` resolves the final path
segment as:

```text
project.directory_name or str(project.id)
```

The string overload of `project_home(project_id)` remains a legacy/explicit ID
lookup and continues resolving to the UUID segment. New creation code must pass
the persisted project object or an explicit reserved directory name when
provisioning a readable directory.

All existing consumers that already pass a `Project` object automatically gain
the new behavior. Call sites that use only a project ID must be reviewed so a
new managed project is never incorrectly routed back to a UUID directory. In
particular, managed-storage updates and API tests that currently reconstruct a
path from only the returned project ID must load or retain the `Project` object.

## Creation Flows

The rule applies to every newly created managed project, including:

- projects created through the HTTP API;
- projects created by agent platform tools;
- an automatically created default `Recent` project;
- demo/bootstrap projects when they create a new managed project.

External and remote creation flows are unchanged. A project converted back to
managed storage keeps its persisted `directory_name` when one exists. A legacy
project with no directory name continues using its UUID rather than receiving a
new name during an update.

## Error Handling

- Invalid or punctuation-only names use the `project` fallback and normal
  suffix allocation.
- Filesystem permission, I/O, and disk-space errors surface through the current
  project-creation error boundary; they are not misreported as name conflicts.
- A collision retries with the next suffix for at most 10,000 candidates.
  Exhaustion returns a clear validation error instead of looping indefinitely.
- Failed database persistence cleans up only a directory positively known to
  have been created by the current request.

## Test Strategy

Implementation will follow TDD. Add failing tests before production changes.

### Unit tests

- English normalization.
- Chinese-to-pinyin transliteration.
- mixed Chinese and Latin input.
- repeated whitespace, punctuation, underscores, and hyphens.
- maximum-length truncation and suffix-aware truncation.
- empty transliteration fallback.
- safe-path output invariant.

### Service and repository tests

- a new managed project persists `directory_name` and creates `data/` and
  `runs/` beneath it;
- duplicate names allocate `-2` and `-3`;
- a pre-existing untracked filesystem directory is skipped;
- database collision retry is safe;
- two independent database sessions concurrently allocate distinct names;
- dangling symlinks and other pre-existing directory entries are skipped;
- non-collision failure cleans up only the newly reserved directory;
- external and remote projects do not allocate managed directory names;
- default and demo creation paths follow the rule;
- renaming a project leaves `directory_name` and its path unchanged.

### Compatibility and migration tests

- a legacy project with `directory_name = NULL` resolves to its UUID directory;
- the Alembic migration upgrades and downgrades cleanly;
- migration-head assertions are updated to the new revision;
- API create/read/update contracts remain compatible;
- path-layout, scheduler, runtime, terminal, file-service, and agent sandbox
  tests continue passing with both readable and legacy roots.

## Verification

From `backend/` run:

```bash
rtk uv sync
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Also run `rtk git diff --check` from the repository root. If broad backend tests
are unavailable because an external runtime dependency is missing, run all
affected unit and service suites and report the exact skipped command and
reason.

## Out Of Scope

- Renaming or migrating existing UUID directories.
- Renaming a directory after the project display name changes.
- Changing external or remote project roots.
- Deleting managed project data when a project record is deleted.
- Exposing user-editable directory names in the API or UI.
