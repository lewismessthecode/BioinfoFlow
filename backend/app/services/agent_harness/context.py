from __future__ import annotations

import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.config import settings
from app.services.agent_harness.history import HistoryEntry, build_history_view
from app.services.model_runtime.contracts import InputPart

_MAX_DISCOVERED_SKILLS = 200
_MAX_SKILL_METADATA_BYTES = 16 * 1024
_MAX_SKILL_SCAN_ENTRIES = _MAX_DISCOVERED_SKILLS * 16
_MAX_SKILL_SCAN_DIRECTORIES = _MAX_DISCOVERED_SKILLS * 4
_MAX_SKILL_SCAN_DEPTH = 32
_MAX_SKILL_PROMPT_BYTES = 64 * 1024
_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
_SKILL_SECTION_PREAMBLE = (
    "## Available skills\n"
    "Skills are reusable procedures. Load one only when relevant by using read "
    "on its SKILL.md path, then follow its referenced files as needed."
)


@dataclass(frozen=True)
class ModelContext:
    instructions: str
    input_items: tuple[InputPart, ...]
    history_revision: int
    compacted: bool = False


class ContextBuilder:
    def build(
        self,
        *,
        prompt_snapshot: str | Mapping[str, Any],
        entries: Iterable[HistoryEntry | Mapping[str, Any]],
        attachment_parts: Iterable[InputPart] = (),
        attachment_parts_by_id: Mapping[str, tuple[InputPart, ...]] | None = None,
    ) -> ModelContext:
        history = build_history_view(
            entries,
            attachment_parts_by_id=attachment_parts_by_id,
        )
        return ModelContext(
            instructions=_prompt_content(prompt_snapshot),
            input_items=(*history.input_items, *attachment_parts),
            history_revision=history.through_sequence,
            compacted=history.compaction_sequence is not None,
        )


def create_prompt_snapshot(
    *,
    core_instructions: str,
    workspace: Mapping[str, Any],
    tool_descriptions: Mapping[str, str],
    project_instructions: Iterable[str] = (),
    skills: Iterable[Mapping[str, str]] = (),
) -> dict[str, Any]:
    sections = [core_instructions.strip()]
    workspace_lines = [
        f"- {key}: {workspace[key]}"
        for key in ("root", "project", "runtime")
        if workspace.get(key) not in {None, ""}
    ]
    if workspace_lines:
        sections.append("## Workspace\n" + "\n".join(workspace_lines))
    tool_lines = [
        f"- {name}: {description.strip()}"
        for name, description in sorted(tool_descriptions.items())
    ]
    if tool_lines:
        sections.append("## Available tools\n" + "\n".join(tool_lines))
    instruction_lines = [item.strip() for item in project_instructions if item.strip()]
    if instruction_lines:
        sections.append("## Project instructions\n" + "\n\n".join(instruction_lines))
    skill_lines = []
    skill_read_roots: set[str] = set()
    for skill in bounded_skill_metadata_for_prompt(skills):
        name = skill.get("name")
        description = skill.get("description")
        path = skill.get("path")
        if name and description and path:
            line = f"- {name}: {description.strip()} ({path})"
            skill_lines.append(line)
            skill_path = Path(path).expanduser()
            if skill_path.is_absolute():
                skill_read_root = _validated_directory_path(skill_path.parent)
                if skill_read_root is not None:
                    skill_read_roots.add(str(skill_read_root))
    if skill_lines:
        sections.append(_SKILL_SECTION_PREAMBLE + "\n" + "\n".join(skill_lines))
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "content": "\n\n".join(sections),
    }
    if skill_read_roots and workspace.get("runtime") == "local":
        snapshot["skill_read_roots"] = sorted(skill_read_roots)
    return snapshot


def bounded_skill_metadata_for_prompt(
    skills: Iterable[Mapping[str, str]],
) -> tuple[Mapping[str, str], ...]:
    accepted: list[Mapping[str, str]] = []
    section_bytes = len(_SKILL_SECTION_PREAMBLE.encode("utf-8"))
    for skill in sorted(
        skills,
        key=lambda item: (item.get("name", ""), item.get("path", "")),
    ):
        name = skill.get("name")
        description = skill.get("description")
        path = skill.get("path")
        if not name or not description or not path:
            continue
        line = f"\n- {name}: {description.strip()} ({path})"
        line_bytes = len(line.encode("utf-8"))
        if section_bytes + line_bytes > _MAX_SKILL_PROMPT_BYTES:
            break
        accepted.append(skill)
        section_bytes += line_bytes
    return tuple(accepted)


def build_session_prompt_snapshot(
    *,
    core_snapshot: Mapping[str, Any],
    workspace: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze the complete stable prompt for one newly-created session."""

    core_content = _prompt_content(core_snapshot)
    root = _local_workspace_root(workspace)
    is_local = workspace.get("runtime") == "local"
    snapshot = create_prompt_snapshot(
        core_instructions=core_content,
        workspace=workspace,
        tool_descriptions=_default_tool_descriptions(),
        project_instructions=(
            _discover_project_instructions(root)
            if is_local
            else _frozen_project_instructions(workspace)
        ),
        skills=_discover_skills(root) if is_local else _frozen_remote_skills(workspace),
    )
    snapshot_id = core_snapshot.get("id")
    if isinstance(snapshot_id, str) and snapshot_id:
        snapshot["id"] = snapshot_id
    return snapshot


def _frozen_project_instructions(
    workspace: Mapping[str, Any],
) -> tuple[str, ...]:
    raw_instructions = workspace.get("project_instructions")
    if not isinstance(raw_instructions, (list, tuple)):
        return ()
    return tuple(
        instruction
        for instruction in raw_instructions
        if isinstance(instruction, str) and instruction.strip()
    )


def _frozen_remote_skills(
    workspace: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    raw_root = workspace.get("root")
    raw_skills = workspace.get("skills")
    if (
        not isinstance(raw_root, str)
        or not raw_root.strip()
        or not isinstance(raw_skills, (list, tuple))
    ):
        return ()
    root = PurePosixPath(raw_root)
    if not root.is_absolute() or ".." in root.parts:
        return ()
    discovered: dict[str, dict[str, str]] = {}
    for raw in raw_skills[:_MAX_DISCOVERED_SKILLS]:
        if not isinstance(raw, Mapping):
            continue
        name = raw.get("name")
        description = raw.get("description")
        raw_path = raw.get("path")
        if not all(
            isinstance(item, str) and item.strip()
            for item in (name, description, raw_path)
        ):
            continue
        assert isinstance(name, str)
        assert isinstance(description, str)
        assert isinstance(raw_path, str)
        path = PurePosixPath(raw_path)
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.name != "SKILL.md"
            or relative.parts[:2] not in {(".agents", "skills"), (".codex", "skills")}
        ):
            continue
        discovered.setdefault(
            name.strip(),
            {
                "name": name.strip(),
                "description": description.strip(),
                "path": str(path),
            },
        )
    return tuple(discovered.values())


def _default_tool_descriptions() -> dict[str, str]:
    from app.services.agent_harness.tools.ask_user import AskUserTool
    from app.services.agent_harness.tools.bash import BashTool
    from app.services.agent_harness.tools.edit import EditTool
    from app.services.agent_harness.tools.read import ReadTool
    from app.services.agent_harness.tools.update_plan import UpdatePlanTool
    from app.services.agent_harness.tools.write import WriteTool

    tools = (
        ReadTool(),
        BashTool(),
        EditTool(),
        WriteTool(),
        AskUserTool(),
        UpdatePlanTool(),
    )
    return {tool.spec.name: tool.spec.description for tool in tools}


def _local_workspace_root(workspace: Mapping[str, Any]) -> Path | None:
    if workspace.get("runtime") != "local":
        return None
    raw_root = workspace.get("root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        return None
    root = Path(raw_root).expanduser().resolve(strict=False)
    return root if root.is_dir() else None


def _discover_project_instructions(root: Path | None) -> tuple[str, ...]:
    if root is None:
        return ()
    for directory in (root, *root.parents):
        for filename in ("AGENTS.md", "CLAUDE.md"):
            candidate = directory / filename
            content = _read_bounded_text(
                candidate,
                max_bytes=settings.agent_project_instructions_max_bytes,
            )
            if content:
                return (f"Instructions from {candidate}:\n\n{content}",)
    return ()


def _discover_skills(root: Path | None) -> tuple[dict[str, str], ...]:
    workspace_roots = (
        (root / ".agents" / "skills", root / ".codex" / "skills")
        if root is not None
        else ()
    )
    configured_root = settings.skills_root
    home = Path.home()
    home_roots = (home / ".agents" / "skills", home / ".codex" / "skills")

    # ``setdefault`` makes the source order the precedence contract:
    # workspace-local skills override the configured platform root, which in
    # turn overrides implicit user-home skills with the same metadata name.
    discovered: dict[str, dict[str, str]] = {}
    sources = [
        *((skills_root, False) for skills_root in workspace_roots),
        (configured_root, True),
        *((skills_root, False) for skills_root in home_roots),
    ]
    scanned_candidates = 0
    scan_budget = {
        "entries": _MAX_SKILL_SCAN_ENTRIES,
        "directories": _MAX_SKILL_SCAN_DIRECTORIES,
    }
    for skills_root, configured in sources:
        skill_files = (
            _configured_skill_files(skills_root, scan_budget=scan_budget)
            if configured
            else _recursive_skill_files(skills_root, scan_budget=scan_budget)
        )
        iterator = iter(skill_files)
        while scanned_candidates < _MAX_DISCOVERED_SKILLS:
            try:
                path = next(iterator)
            except StopIteration:
                break
            scanned_candidates += 1
            metadata = _skill_metadata(path)
            if metadata is not None:
                discovered.setdefault(metadata["name"], metadata)
        if scanned_candidates >= _MAX_DISCOVERED_SKILLS:
            break
        if scan_budget["entries"] <= 0:
            break
        if scan_budget["directories"] <= 0:
            break
    return tuple(discovered.values())


def _configured_skill_files(
    root: Path,
    *,
    scan_budget: dict[str, int],
) -> Iterable[Path]:
    """Return only trusted ``root/<skill>/SKILL.md`` files.

    The configured root is a platform capability boundary. Symlinked roots,
    skill directories, and metadata files are ignored so discovery cannot
    advertise a path outside that boundary.
    """

    return _iter_skill_files(
        root,
        minimum_depth=1,
        maximum_depth=1,
        scan_budget=scan_budget,
    )


def _recursive_skill_files(
    root: Path,
    *,
    scan_budget: dict[str, int],
) -> Iterable[Path]:
    return _iter_skill_files(
        root,
        minimum_depth=0,
        maximum_depth=_MAX_SKILL_SCAN_DEPTH,
        scan_budget=scan_budget,
    )


def _iter_skill_files(
    root: Path,
    *,
    minimum_depth: int,
    maximum_depth: int | None,
    scan_budget: dict[str, int],
) -> Iterable[Path]:
    pending = [(root, 0)]
    while pending and scan_budget["entries"] > 0 and scan_budget["directories"] > 0:
        directory, depth = pending.pop()
        directory_descriptor = None
        entries: list[tuple[str, bool, bool]] = []
        scan_budget["directories"] -= 1
        try:
            directory_descriptor = os.open(directory, _DIRECTORY_OPEN_FLAGS)
            with os.scandir(directory_descriptor) as stream:
                while scan_budget["entries"] > 0:
                    try:
                        entry = next(stream)
                    except StopIteration:
                        break
                    scan_budget["entries"] -= 1
                    try:
                        if entry.is_symlink():
                            continue
                        entries.append(
                            (
                                entry.name,
                                entry.is_dir(follow_symlinks=False),
                                entry.is_file(follow_symlinks=False),
                            )
                        )
                    except OSError:
                        continue
        except OSError:
            continue
        finally:
            if directory_descriptor is not None:
                os.close(directory_descriptor)

        child_directories = []
        for name, is_directory, is_file in sorted(entries, key=lambda item: item[0]):
            path = directory / name
            if is_file and name == "SKILL.md" and depth >= minimum_depth:
                yield path
                continue
            if is_directory and (maximum_depth is None or depth < maximum_depth):
                child_directories.append(path)
        for child in reversed(child_directories):
            pending.append((child, depth + 1))


def _skill_metadata(path: Path) -> dict[str, str] | None:
    content = _read_bounded_text(
        path,
        max_bytes=_MAX_SKILL_METADATA_BYTES,
        reject_oversized=True,
        encoding_errors="strict",
    )
    if not content or not content.startswith("---\n"):
        return None
    boundary = content.find("\n---", 4)
    if boundary < 0:
        return None
    fields: dict[str, str] = {}
    for line in content[4:boundary].splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            fields[key.strip()] = value.strip().strip("\"'")
    name = fields.get("name")
    description = fields.get("description")
    if not name or not description:
        return None
    return {"name": name, "description": description, "path": str(path)}


def _read_bounded_text(
    path: Path,
    *,
    max_bytes: int,
    reject_oversized: bool = False,
    encoding_errors: str = "replace",
) -> str | None:
    directory_descriptor = None
    descriptor = None
    try:
        directory_descriptor = _open_directory_without_symlinks(path.parent)
        descriptor = os.open(
            path.name,
            _FILE_OPEN_FLAGS,
            dir_fd=directory_descriptor,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        text = data[:max_bytes].decode("utf-8", errors=encoding_errors).strip()
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    if not data:
        return None
    truncated = len(data) > max_bytes
    if truncated and reject_oversized:
        return None
    if truncated:
        text += "\n\n[Project instructions truncated at the configured byte limit.]"
    return text or None


def _validated_directory_path(path: Path) -> Path | None:
    descriptor = None
    try:
        descriptor = _open_directory_without_symlinks(path)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return path


def _open_directory_without_symlinks(path: Path) -> int:
    """Open an absolute directory by pinning every ancestor descriptor."""

    if not path.is_absolute():
        raise OSError("secure directory traversal requires an absolute path")
    parts = path.parts
    descriptor = os.open(parts[0], _DIRECTORY_OPEN_FLAGS)
    try:
        for part in parts[1:]:
            child_descriptor = os.open(
                part,
                _DIRECTORY_OPEN_FLAGS,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child_descriptor
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _prompt_content(snapshot: str | Mapping[str, Any]) -> str:
    if isinstance(snapshot, str):
        return snapshot
    content = snapshot.get("content")
    if not isinstance(content, str):
        raise ValueError("prompt snapshot must contain string content")
    return content
