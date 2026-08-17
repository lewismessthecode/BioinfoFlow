"""Verify the production disposable-container Agent Bash boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shlex

from app.config import settings
from app.services.agent_harness.sandbox.container_executor import (
    DockerSandboxExecutor,
)


async def _run(*, image: str, workspace: Path) -> None:
    executor = DockerSandboxExecutor(image=image)
    state_root = shlex.quote(str(settings.state_root))

    async def execute(mode: str, command: str):
        return await executor.execute(
            argv=["/bin/bash", "--noprofile", "--norc", "-c", command],
            cwd=workspace,
            workspace_root=workspace,
            environment={"PATH": "/usr/local/bin:/usr/bin:/bin"},
            mode=mode,
            timeout_seconds=15,
            capture_limit=65_536,
            cancellation=None,
            cwd_inode=workspace.stat().st_ino,
            workspace_inode=workspace.stat().st_ino,
        )

    denied = await execute(
        "read-only",
        f"test ! -S /var/run/docker.sock && test ! -e {state_root} && touch denied.txt",
    )
    allowed = await execute(
        "workspace-write",
        f"test ! -S /var/run/docker.sock && test ! -e {state_root} "
        "&& touch allowed.txt && printf ready",
    )
    confined_root = await execute(
        "workspace-write",
        "touch /bioinfoflow-default-root-write",
    )
    escalated_root = await execute(
        "danger-full-access",
        "test ! -S /var/run/docker.sock && touch /bioinfoflow-escalated-root-write",
    )

    assert denied.exit_code != 0
    assert not (workspace / "denied.txt").exists()
    assert allowed.exit_code == 0 and allowed.stdout == "ready", allowed
    assert (workspace / "allowed.txt").exists()
    assert confined_root.exit_code != 0
    assert escalated_root.exit_code == 0
    assert allowed.sandbox["enforcement"] == "full"
    print(
        json.dumps(
            {
                "adapter": allowed.sandbox["adapter"],
                "docker_socket_in_child": False,
                "enforcement": allowed.sandbox["enforcement"],
                "execution": "disposable-container",
                "read_only_exit": denied.exit_code,
                "workspace_write_exit": allowed.exit_code,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    workspace = arguments.workspace.expanduser().resolve(strict=True)
    asyncio.run(_run(image=arguments.image, workspace=workspace))


if __name__ == "__main__":
    main()
