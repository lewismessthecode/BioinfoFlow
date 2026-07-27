# Readable Managed Project Directories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store every newly created managed BioinfoFlow project in a stable, readable ASCII directory derived from its project name, while leaving all existing UUID directories unchanged.

**Architecture:** Persist an immutable nullable `Project.directory_name`; legacy null rows resolve through the existing UUID fallback. A focused naming utility produces pinyin-aware kebab-case candidates, and a managed-directory allocator coordinates the database unique constraint with atomic filesystem reservation before callers commit their surrounding transaction.

**Tech Stack:** Python 3.13, FastAPI service layer, SQLAlchemy async, Alembic, SQLite/PostgreSQL, `pypinyin`, pytest, Ruff, uv.

---

## File Map

- Create `backend/app/utils/project_directory_names.py`: deterministic transliteration and suffix-aware candidate generation.
- Create `backend/tests/test_utils/test_project_directory_names.py`: naming-rule unit tests.
- Create `backend/alembic/versions/0056_readable_project_directories.py`: nullable column and global uniqueness migration.
- Create `backend/tests/test_migrations/test_readable_project_directories.py`: populated-database upgrade/downgrade coverage.
- Modify `backend/app/models/project.py`: persist the immutable internal directory name.
- Modify `backend/app/path_layout.py`: resolve managed `Project` objects through the readable name with UUID fallback.
- Modify `backend/tests/test_path_layout.py`: readable, legacy, external, and remote path contracts.
- Create `backend/app/services/project_directory_service.py`: collision-safe DB/filesystem allocation and cleanup.
- Create `backend/tests/test_services/test_project_directory_service.py`: sequential, concurrent, filesystem-collision, and cleanup tests.
- Modify `backend/app/services/project_service.py`: route ordinary and default managed project creation through the allocator.
- Modify `backend/tests/test_services/test_project_service.py`: managed/default/external/remote and rename stability tests.
- Modify `backend/app/services/demo_bootstrap_service.py`: allocate readable paths for newly created demo projects without backfilling existing demos.
- Modify `backend/tests/test_api/test_first_run.py`: demo creation and existing-demo compatibility coverage.
- Modify `backend/tests/test_api/test_projects.py`: API-level readable path and rename behavior.
- Modify `backend/tests/test_api/test_agent_core_api.py`: stop reconstructing a new project path from only its UUID.
- Modify `backend/tests/test_migrations/test_agent_permission_upgrade_compatibility.py`: advance the asserted migration head.
- Modify `backend/pyproject.toml` and `backend/uv.lock`: add and lock `pypinyin`.

### Task 1: Add the pinyin-aware directory naming utility

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/app/utils/project_directory_names.py`
- Create: `backend/tests/test_utils/test_project_directory_names.py`

- [ ] **Step 1: Add failing naming tests**

Create parametrized tests for the approved examples and edge cases:

```python
import pytest

from app.utils.project_directory_names import (
    project_directory_base,
    project_directory_candidate,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("BioinfoFlow Demo", "bioinfoflow-demo"),
        ("测试", "ce-shi"),
        ("肿瘤 RNA 分析", "zhong-liu-rna-fen-xi"),
        ("  Demo___Project  ", "demo-project"),
        ("Café", "cafe"),
        ("🧬🧪", "project"),
    ],
)
def test_project_directory_base(name: str, expected: str) -> None:
    assert project_directory_base(name) == expected


def test_project_directory_candidate_preserves_maximum_length() -> None:
    base = "a" * 100
    assert project_directory_candidate(base, 1) == base
    assert project_directory_candidate(base, 2) == f"{'a' * 98}-2"
    assert len(project_directory_candidate(base, 10_000)) == 100


def test_project_directory_candidate_rejects_invalid_ordinal() -> None:
    with pytest.raises(ValueError, match="ordinal"):
        project_directory_candidate("project", 0)
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_utils/test_project_directory_names.py -q
```

Expected: FAIL during collection because `project_directory_names` does not exist.

- [ ] **Step 3: Add and lock `pypinyin`**

Run from `backend/`:

```bash
rtk uv add pypinyin
```

Expected: `pyproject.toml` contains `pypinyin` and `uv.lock` records the resolved package.

- [ ] **Step 4: Implement the minimal deterministic helper**

Create `backend/app/utils/project_directory_names.py` with these public contracts:

```python
from __future__ import annotations

import re
import unicodedata

from pypinyin import Style, lazy_pinyin


MAX_PROJECT_DIRECTORY_LENGTH = 100
_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


def _ascii_fallback(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def project_directory_base(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(name or "").strip())
    transliterated = " ".join(
        lazy_pinyin(normalized, style=Style.NORMAL, errors=_ascii_fallback)
    ).lower()
    slug = _SEPARATOR_RE.sub("-", transliterated).strip("-")
    slug = slug[:MAX_PROJECT_DIRECTORY_LENGTH].rstrip("-")
    return slug or "project"


def project_directory_candidate(base: str, ordinal: int) -> str:
    if ordinal < 1:
        raise ValueError("ordinal must be at least 1")
    suffix = "" if ordinal == 1 else f"-{ordinal}"
    prefix_length = MAX_PROJECT_DIRECTORY_LENGTH - len(suffix)
    prefix = base[:prefix_length].rstrip("-") or "project"[:prefix_length]
    return f"{prefix}{suffix}"
```

- [ ] **Step 5: Run naming tests and Ruff**

```bash
rtk uv run pytest tests/test_utils/test_project_directory_names.py -q
rtk uv run ruff check app/utils/project_directory_names.py tests/test_utils/test_project_directory_names.py
```

Expected: PASS.

- [ ] **Step 6: Commit the naming unit**

```bash
rtk git add backend/pyproject.toml backend/uv.lock backend/app/utils/project_directory_names.py backend/tests/test_utils/test_project_directory_names.py
rtk git commit -m "feat: add readable project directory names"
```

### Task 2: Persist the directory identity and preserve legacy path resolution

**Files:**
- Create: `backend/alembic/versions/0056_readable_project_directories.py`
- Create: `backend/tests/test_migrations/test_readable_project_directories.py`
- Modify: `backend/tests/test_migrations/test_agent_permission_upgrade_compatibility.py`
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/path_layout.py`
- Modify: `backend/tests/test_path_layout.py`

- [ ] **Step 1: Add failing model and path-layout tests**

Cover both generations explicitly:

```python
from app.models.project import Project
from app.path_layout import project_home


def test_managed_project_uses_persisted_directory_name(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    project = Project(id="00000000-0000-0000-0000-000000000111", name="测试", user_id="dev")
    project.directory_name = "ce-shi"
    assert project_home(project) == home / "projects" / "ce-shi"


def test_legacy_managed_project_without_directory_name_uses_uuid(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    project_id = "00000000-0000-0000-0000-000000000112"
    project = Project(id=project_id, name="Legacy", user_id="dev")
    assert project_home(project) == home / "projects" / project_id
    assert project_home(project_id) == home / "projects" / project_id
```

Retain external-path assertions and confirm remote projects still raise `BadRequestError`.

- [ ] **Step 2: Run path tests and verify failure**

```bash
rtk uv run pytest tests/test_path_layout.py -q
```

Expected: FAIL because `Project.directory_name` and readable resolution are absent.

- [ ] **Step 3: Add the nullable immutable model field and path fallback**

In `Project`, add:

```python
directory_name: Mapped[str | None] = mapped_column(
    String(120), nullable=True, unique=True
)
```

In the managed branch of `project_home(Project)`, resolve and validate:

```python
directory_name = safe_path_name(
    str(getattr(project, "directory_name", None) or project.id),
    field_name="project directory name",
)
return (projects_root() / directory_name).resolve()
```

Do not change the string overload: `project_home(project_id)` must remain UUID-based.

- [ ] **Step 4: Add the migration and populated-database test**

Create revision `0056_readable_project_directories` with
`down_revision = "0055_merge_agent_heads"`. Upgrade adds nullable
`projects.directory_name VARCHAR(120)` and unique index
`uq_projects_directory_name`; downgrade removes the index and column.

The migration test must:

1. upgrade a temporary SQLite database to `0055_merge_agent_heads`;
2. insert a legacy project row;
3. upgrade to `0056_readable_project_directories`;
4. assert the legacy value is null;
5. insert two additional null values successfully;
6. assert duplicate non-null `ce-shi` values fail;
7. downgrade and assert the column is gone.

Update `EXPECTED_HEAD` to `0056_readable_project_directories`.

- [ ] **Step 5: Run path and migration tests**

```bash
rtk uv run pytest tests/test_path_layout.py tests/test_migrations/test_readable_project_directories.py tests/test_migrations/test_agent_permission_upgrade_compatibility.py -q
rtk uv run ruff check app/models/project.py app/path_layout.py alembic/versions/0056_readable_project_directories.py tests/test_path_layout.py tests/test_migrations/test_readable_project_directories.py
```

Expected: PASS.

- [ ] **Step 6: Commit persistence and compatibility**

```bash
rtk git add backend/app/models/project.py backend/app/path_layout.py backend/alembic/versions/0056_readable_project_directories.py backend/tests/test_path_layout.py backend/tests/test_migrations/test_readable_project_directories.py backend/tests/test_migrations/test_agent_permission_upgrade_compatibility.py
rtk git commit -m "feat: persist managed project directory names"
```

### Task 3: Allocate managed directories safely across database and filesystem collisions

**Files:**
- Create: `backend/app/services/project_directory_service.py`
- Create: `backend/tests/test_services/test_project_directory_service.py`
- Modify: `backend/app/repositories/project_repo.py`

- [ ] **Step 1: Add failing allocator tests**

Use file-backed SQLite and two independent `AsyncSession` objects. Cover:

```python
@pytest.mark.asyncio
async def test_allocate_uses_base_then_numeric_suffix(db_session):
    first = await allocator(db_session).add_pending(project_data("测试"))
    await db_session.commit()
    second = await allocator(db_session).add_pending(project_data("测试"))
    await db_session.commit()
    assert first.project.directory_name == "ce-shi"
    assert second.project.directory_name == "ce-shi-2"


@pytest.mark.asyncio
async def test_allocate_skips_existing_directory_and_dangling_symlink(
    db_session, tmp_path, monkeypatch
):
    (projects_root() / "ce-shi").mkdir(parents=True)
    (projects_root() / "ce-shi-2").symlink_to(projects_root() / "missing")
    reservation = await allocator(db_session).add_pending(project_data("测试"))
    assert reservation.project.directory_name == "ce-shi-3"


@pytest.mark.asyncio
async def test_concurrent_allocations_receive_distinct_names(db_engine):
    # Start two allocators with independent sessions and commit both.
    # Assert the persisted names are exactly {"ce-shi", "ce-shi-2"}.
```

Also simulate an unrelated `IntegrityError` and assert it propagates, while a
`uq_projects_directory_name` collision retries. Simulate layout failure and
assert the allocator rolls back the row and removes only its own reservation.

- [ ] **Step 2: Run allocator tests and verify failure**

```bash
rtk uv run pytest tests/test_services/test_project_directory_service.py -q
```

Expected: FAIL because the allocator does not exist.

- [ ] **Step 3: Add the repository conflict query and allocator contracts**

Add a repository method for diagnostics/fast skipping:

```python
async def directory_name_exists(self, directory_name: str) -> bool:
    stmt = select(self.model.id).where(
        self.model.directory_name == directory_name
    ).limit(1)
    return await self.session.scalar(stmt) is not None
```

Create these allocator interfaces:

```python
@dataclass(slots=True)
class ManagedProjectReservation:
    project: Project
    root: Path
    created_root: bool = True


class ProjectDirectoryService:
    MAX_CANDIDATES = 10_000

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)
```

Implement these exact public methods on the class:

- `add_pending(self, data: dict) -> ManagedProjectReservation`
- `commit(self, reservation: ManagedProjectReservation) -> Project`
- `discard(self, reservation: ManagedProjectReservation) -> None`

`add_pending()` must, for each ordinal:

1. generate the suffix-aware candidate;
2. use `Path.lstat()` semantics to reject every existing entry, including a dangling symlink;
3. use `session.begin_nested()` plus `repo.add()` to flush the candidate row;
4. retry only when `_is_directory_name_integrity_error()` matches PostgreSQL constraint `uq_projects_directory_name` or SQLite text `unique constraint failed: projects.directory_name`;
5. atomically create the root with `mkdir(parents=True, exist_ok=False)`;
6. call `ensure_project_layout(project)` and return the reservation.

If the atomic `mkdir` loses a race, delete and flush the pending row, then try
the next candidate. `commit()` must roll back and clean the reservation if the
commit fails. `discard()` must roll back the row and remove only the root created
by that reservation; it must not follow symlinks or delete a pre-existing path.

- [ ] **Step 4: Run allocator tests and Ruff**

```bash
rtk uv run pytest tests/test_services/test_project_directory_service.py -q
rtk uv run ruff check app/services/project_directory_service.py app/repositories/project_repo.py tests/test_services/test_project_directory_service.py
```

Expected: PASS, including the two-session concurrency test.

- [ ] **Step 5: Commit the allocator**

```bash
rtk git add backend/app/services/project_directory_service.py backend/app/repositories/project_repo.py backend/tests/test_services/test_project_directory_service.py
rtk git commit -m "feat: allocate unique project directories"
```

### Task 4: Route ordinary, default, and demo managed projects through the allocator

**Files:**
- Modify: `backend/app/services/project_service.py`
- Modify: `backend/app/services/demo_bootstrap_service.py`
- Modify: `backend/tests/test_services/test_project_service.py`
- Modify: `backend/tests/test_api/test_first_run.py`
- Modify: `backend/tests/test_api/test_projects.py`
- Modify: `backend/tests/test_api/test_agent_core_api.py`

- [ ] **Step 1: Add failing service and API tests**

Add assertions that:

- creating `COVID Analysis` persists `covid-analysis` and creates
  `projects/covid-analysis/{data,runs}`;
- the next identical project uses `covid-analysis-2`;
- a new default project uses `recent` but an existing default with a null field
  keeps its UUID path;
- renaming `COVID Analysis` to `Renamed` leaves `directory_name` and
  `project_home(project)` unchanged;
- external and remote projects keep `directory_name is None`;
- a fresh demo uses `bioinfoflow-demo`, while an already present legacy demo
  with a null field stays at its deterministic UUID path;
- fresh demos in two workspaces receive the globally unique names
  `bioinfoflow-demo` and `bioinfoflow-demo-2`;
- API responses still expose `project_root = "asset://project"` and do not
  expose `directory_name`.

In `test_agent_fs_tree_defaults_to_project_home`, load the created `Project`
from the database and call `project_home(project)` instead of
`project_home(project_id)`.

- [ ] **Step 2: Run focused tests and verify the new assertions fail**

```bash
rtk uv run pytest tests/test_services/test_project_service.py tests/test_api/test_projects.py tests/test_api/test_first_run.py tests/test_api/test_agent_core_api.py::test_agent_fs_tree_defaults_to_project_home -q
```

Expected: FAIL because creation flows still provision UUID roots.

- [ ] **Step 3: Integrate `ProjectService`**

For ordinary managed creation, replace UUID layout provisioning plus
`repo.create()` with:

```python
reservation = await ProjectDirectoryService(self.repo.session).add_pending(data)
return await ProjectDirectoryService(self.repo.session).commit(reservation)
```

Reuse one allocator instance in the real code. Route `get_or_create_default()`
through the same pending allocator with name `Recent`; retain its existing
unique-default race recovery. When `update_project()` switches storage mode to
`managed`,
pass the full project object to `ensure_project_layout(project)` so readable
projects never fall back to the UUID path. Do not assign a directory name to a
legacy project during rename or storage updates.

- [ ] **Step 4: Integrate demo bootstrap without weakening its transaction**

When the deterministic demo project is absent, use
`ProjectDirectoryService.add_pending()` with the existing deterministic ID and
`Bioinfoflow Demo` name. Continue building demo files, workflow, binding, and
pin in the current transaction, then commit once. If any later step fails,
rollback and call `discard()` for the reservation before retrying or re-raising.
When the demo row already exists, do not populate its null `directory_name`.

- [ ] **Step 5: Run focused integration tests and Ruff**

```bash
rtk uv run pytest tests/test_services/test_project_service.py tests/test_api/test_projects.py tests/test_api/test_first_run.py tests/test_api/test_agent_core_api.py::test_agent_fs_tree_defaults_to_project_home -q
rtk uv run ruff check app/services/project_service.py app/services/demo_bootstrap_service.py tests/test_services/test_project_service.py tests/test_api/test_projects.py tests/test_api/test_first_run.py tests/test_api/test_agent_core_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit creation-flow integration**

```bash
rtk git add backend/app/services/project_service.py backend/app/services/demo_bootstrap_service.py backend/tests/test_services/test_project_service.py backend/tests/test_api/test_projects.py backend/tests/test_api/test_first_run.py backend/tests/test_api/test_agent_core_api.py
rtk git commit -m "feat: create projects in readable directories"
```

### Task 5: Verify the complete backend path contract

**Files:**
- Modify only files required by failures attributable to this feature.

- [ ] **Step 1: Run the affected path and service suites**

```bash
rtk uv run pytest tests/test_path_layout.py tests/test_path_layout_security.py tests/test_engine/test_path_contract.py tests/test_services/test_project_service.py tests/test_services/test_project_directory_service.py tests/test_api/test_projects.py tests/test_api/test_first_run.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full backend suite**

```bash
rtk uv run pytest
```

Expected: PASS. Diagnose every failure against the readable/legacy dual-path contract; do not loosen unrelated assertions.

- [ ] **Step 3: Run static and migration verification**

```bash
rtk uv run alembic upgrade head
rtk uv run ruff check .
rtk uv run ruff format --check .
rtk uv run bif --version
```

Expected: PASS.

- [ ] **Step 4: Run repository hygiene checks**

From the repository root:

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors and only intentional feature changes.

- [ ] **Step 5: Commit any verification-only corrections**

If verification required code changes, stage only those exact files and commit:

```bash
rtk git commit -m "test: cover readable project paths"
```

If no correction was required, do not create an empty commit.

### Task 6: Independent review, remote sync, and pull request

**Files:**
- Modify only files required to address validated review findings.

- [ ] **Step 1: Request independent reviews**

Dispatch one reviewer for spec/requirement compliance and one reviewer for code
quality, concurrency, filesystem safety, and migration compatibility. Require
file-and-line evidence for every finding.

- [ ] **Step 2: Validate and address findings with TDD**

For each valid finding, first add or tighten a failing test, run it to confirm
the failure, implement the smallest fix, and rerun the focused suite. Reject
findings contradicted by the approved design or current code evidence.

- [ ] **Step 3: Re-run final verification**

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
rtk git diff --check
```

Expected: PASS.

- [ ] **Step 4: Sync the remote default branch before publishing**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: branch is based on current `origin/main`; resolve any conflicts while preserving the readable/legacy path contract, then rerun final verification if the rebase changed the base.

- [ ] **Step 5: Push and create the PR**

Create `/tmp/readable-project-directories-pr.md` with `apply_patch` using this
body, replacing each verification status only with the result actually run:

```markdown
## Summary

- create new managed projects in stable ASCII directories derived from their names
- transliterate Chinese names to pinyin and add numeric suffixes for global collisions
- preserve UUID directories for every existing project and keep directory identity stable across renames

## Compatibility

- no backfill or filesystem migration
- external and remote project roots are unchanged
- the internal directory name is not exposed through create, update, or read APIs

## Verification

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `git diff --check`

## Review

- independent requirements review completed
- independent concurrency, filesystem-safety, and migration review completed
```

Then run:

```bash
rtk git push -u origin codex/readable-project-directories
rtk gh pr create --base main --head codex/readable-project-directories --title "feat: use readable project directories" --body-file /tmp/readable-project-directories-pr.md
```

The PR body must summarize behavior, legacy compatibility, migration, TDD
coverage, independent review results, and exact verification commands. Do not
edit `CHANGELOG.md`.
