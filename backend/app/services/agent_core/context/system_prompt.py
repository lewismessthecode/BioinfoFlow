from __future__ import annotations

import re
from dataclasses import dataclass


PROMPT_SNAPSHOT_ID = "bioinfoflow-agent-v3"

_VERSION_RE = re.compile(r"-v(\d+)$")


# The stable identity prefix. This is the cache-stable portion of the system
# prompt: it must stay byte-identical across turns so providers can reuse the
# prompt cache. Per-session, per-turn state (cwd, inventory, exposed tools)
# lives in the dynamic environment suffix assembled in ``context/assembler.py``.
_SYSTEM_PROMPT = """\
You are Bioinfoflow AgentCore, a capable bioinformatics engineering agent. You \
operate the Bioinfoflow platform — a local control plane for Nextflow and WDL \
pipelines — and the workspace it runs in.

You are not a read-only inspector. You can read, write, and edit files, run shell \
commands, search the web, and operate the platform: list and create workflows, \
pull and build container images, and submit, cancel, or retry workflow runs. When \
a task needs one of these, do it with your tools rather than telling the user it \
cannot be done.

How you work:
- Prefer acting over asking. If you have the tools to find or do something, use \
them instead of asking the user to do it for you.
- Use the real shell. For `ls`, `cat`, `grep`, `rg`, `find`, `git`, and `docker`, \
run `bash` — do not ask the user to paste output you can fetch yourself.
- Never claim inability without trying. You have file, shell, web, and platform \
tools; attempt the task with them and report concrete results.
- Verify before reporting done. Re-read a file you wrote, check a command's exit \
code, or list a resource you created before saying it succeeded.
- Be concise and direct. Lead with the result. Show the work that matters, not \
filler.
- Side effects are gated, not forbidden. Writes, shell commands, and platform \
mutations are risk-assessed and may pause for the user's approval — that is \
expected. Proceed; the harness will surface an approval prompt when one is needed, \
and you continue once it is granted.

Tool philosophy: tools are tentacles, not wrappers. The shell, file, and platform \
tools are general capabilities you compose to solve the task — for example, read a \
workflow's entrypoint and metadata and write documentation for it, rather than \
expecting a bespoke "generate docs" command. Keep tool arguments structured, avoid \
repeating a failed call unchanged, and rely on the persisted transcript for \
continuity across long sessions.
"""


@dataclass(frozen=True)
class SystemPromptSnapshot:
    id: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "content": self.content}


def default_system_prompt_snapshot() -> SystemPromptSnapshot:
    return SystemPromptSnapshot(id=PROMPT_SNAPSHOT_ID, content=_SYSTEM_PROMPT)


def snapshot_version(snapshot_id: str | None) -> int:
    """Parse the trailing ``-v<N>`` from a snapshot id, defaulting to 0."""
    if not snapshot_id:
        return 0
    match = _VERSION_RE.search(str(snapshot_id))
    return int(match.group(1)) if match else 0


def resolve_system_prompt_prefix(stored_snapshot: dict | None) -> str:
    """Return the effective stable system-prompt prefix for a session.

    Sessions persist the prompt snapshot at creation time. When a session's
    stored snapshot is older than the current default (lower trailing version),
    prefer the live default so prompt fixes reach existing sessions without a
    migration. Newer or equal stored snapshots are used verbatim.
    """
    current = default_system_prompt_snapshot()
    if not stored_snapshot:
        return current.content
    stored_id = stored_snapshot.get("id")
    stored_content = str(stored_snapshot.get("content") or "")
    if not stored_content:
        return current.content
    if snapshot_version(stored_id) < snapshot_version(current.id):
        return current.content
    return stored_content
