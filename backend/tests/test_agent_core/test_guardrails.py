from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "backend" / "app"

NEW_CODE_PATHS = [
    BACKEND_APP / "services" / "agent_core",
    BACKEND_APP / "services" / "bioinformatics",
    BACKEND_APP / "services" / "llm",
    BACKEND_APP / "schemas" / "agent_core.py",
    BACKEND_APP / "schemas" / "llm.py",
    BACKEND_APP / "api" / "v1" / "llm.py",
    BACKEND_APP / "cli" / "commands" / "agent.py",
]

NEW_CODE_GLOBS = [
    "backend/app/models/agent_core_*.py",
    "backend/app/models/llm_*.py",
    "backend/app/repositories/agent_core_*.py",
    "backend/app/repositories/llm_*.py",
]

AGENT_EXECUTION_PATHS = [
    BACKEND_APP / "services" / "agent_core",
    BACKEND_APP / "services" / "bioinformatics",
]

LEGACY_IMPLEMENTATION_PATHS = [
    BACKEND_APP / "services" / "agent",
    BACKEND_APP / "services" / "hermes_service",
]

LEGACY_IMPORT_PATTERNS = [
    re.compile(r"^\s*from\s+app\.services\.agent(\.|\s+import\b)", re.MULTILINE),
    re.compile(r"^\s*import\s+app\.services\.agent(\.|\s|$)", re.MULTILINE),
    re.compile(
        r"^\s*from\s+app\.services\.hermes_service(\.|\s+import\b)",
        re.MULTILINE,
    ),
    re.compile(r"^\s*import\s+app\.services\.hermes_service(\.|\s|$)", re.MULTILINE),
]

LEGACY_SEMANTIC_PATTERNS = [
    re.compile(r"\bAgentConversation[A-Za-z_]*\b"),
    re.compile(r"\bAgentMessageRead\b"),
    re.compile(r"\bAgentEventData\b"),
    re.compile(r"\bexecution_policy\b"),
    re.compile(r"\bstorage_backend\b"),
    re.compile(r"\bhermes_session_id\b"),
    re.compile(r"\bassistant_message_id\b"),
    re.compile(r"\bresponse_id\b"),
    re.compile(r"\bAgentResponseHandle\b"),
    re.compile(r"\bAgentApprovalHandle\b"),
]

BIF_SHELL_OUT_PATTERNS = [
    re.compile(r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\([^)]*\bbif\b", re.DOTALL),
    re.compile(r"\basyncio\.create_subprocess_(?:exec|shell)\s*\([^)]*\bbif\b", re.DOTALL),
    re.compile(r"\bshlex\.split\s*\([^)]*\bbif\b", re.DOTALL),
]

SELF_HTTP_PATTERNS = [
    re.compile(r"\bhttpx\.(?:AsyncClient|Client|get|post|put|patch|delete)\b"),
    re.compile(r"\brequests\.(?:get|post|put|patch|delete)\b"),
    re.compile(r"http://(?:localhost|127\.0\.0\.1|\[::1\])"),
    re.compile(r"/api/v1/"),
]


def _guarded_python_files(
    *,
    paths: list[Path] | None = None,
    globs: list[str] | None = None,
) -> list[Path]:
    files: list[Path] = []
    for path in paths or NEW_CODE_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))

    for pattern in globs or NEW_CODE_GLOBS:
        files.extend(REPO_ROOT.glob(pattern))

    return sorted({path for path in files if path.is_file()})


def _violations(
    patterns: list[re.Pattern[str]],
    *,
    paths: list[Path] | None = None,
    globs: list[str] | None = None,
) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for path in _guarded_python_files(paths=paths, globs=globs):
        text = path.read_text(encoding="utf-8")
        path_matches = [
            pattern.pattern for pattern in patterns if pattern.search(text)
        ]
        if path_matches:
            matches[str(path.relative_to(REPO_ROOT))] = path_matches
    return matches


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for path in BACKEND_APP.rglob("*.py"):
        if any(path.is_relative_to(legacy) for legacy in LEGACY_IMPLEMENTATION_PATHS):
            continue
        files.append(path)
    return sorted(files)


def _production_violations(patterns: list[re.Pattern[str]]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for path in _production_python_files():
        text = path.read_text(encoding="utf-8")
        path_matches = [
            pattern.pattern for pattern in patterns if pattern.search(text)
        ]
        if path_matches:
            matches[str(path.relative_to(REPO_ROOT))] = path_matches
    return matches


def test_new_agent_core_code_does_not_import_legacy_agent_or_hermes() -> None:
    assert _violations(LEGACY_IMPORT_PATTERNS) == {}


def test_production_code_does_not_import_legacy_agent_or_hermes() -> None:
    assert _production_violations(LEGACY_IMPORT_PATTERNS) == {}


def test_legacy_agent_service_directories_are_removed() -> None:
    assert [path for path in LEGACY_IMPLEMENTATION_PATHS if path.exists()] == []


def test_new_agent_core_code_does_not_reintroduce_legacy_agent_semantics() -> None:
    assert _violations(LEGACY_SEMANTIC_PATTERNS) == {}


def test_new_agent_core_tools_do_not_shell_out_to_bif() -> None:
    assert _violations(
        BIF_SHELL_OUT_PATTERNS,
        paths=AGENT_EXECUTION_PATHS,
        globs=[],
    ) == {}


def test_new_agent_core_tools_do_not_call_own_fastapi_over_http() -> None:
    assert _violations(
        SELF_HTTP_PATTERNS,
        paths=AGENT_EXECUTION_PATHS,
        globs=[],
    ) == {}
