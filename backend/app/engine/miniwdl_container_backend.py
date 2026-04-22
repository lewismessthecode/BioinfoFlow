from __future__ import annotations

import logging
import os
from pathlib import Path

import docker
from WDL.runtime.backend.docker_swarm import SwarmContainer

from app.engine.miniwdl_mounts import (
    configured_run_mounts,
    configured_shared_mounts,
)


class BioinfoflowSwarmContainer(SwarmContainer):
    """
    Identity-mount shared storage bridging for task containers.

    miniwdl only bind-mounts declared `File`/`Directory` inputs plus the task
    working directory. Production WDLs (e.g. Deaf_20) propagate fastq/bam/ref
    paths through sample sheets as plain strings, so the task container must
    also be able to open those paths. Under Path Contract v3 (identity mount)
    host path == container path, so we bind the platform's shared storage
    roots straight through — no translation, no symlink bridges.
    """

    def prepare_mounts(self, logger: logging.Logger) -> list[docker.types.Mount]:
        mounts = super().prepare_mounts(logger)
        existing_targets = {str(mount["Target"]) for mount in mounts}

        configured = (
            *configured_shared_mounts(),
            *configured_run_mounts(self.host_dir),
        )
        # NOTICE (level 25) is miniwdl's default-visible level. Using INFO
        # hides these lines in deployed logs, leaving no trail when a task
        # fails because the platform mounts were missing.
        logger.log(
            25,
            "bioinfoflow_docker_swarm prepare_mounts :: host_dir=%s configured=%d",
            self.host_dir,
            len(configured),
        )

        for mapping in configured:
            target = str(mapping.container_root)
            source = str(mapping.host_root)
            if target in existing_targets:
                logger.log(
                    25,
                    "bioinfoflow mount skipped (target already mounted) :: %s",
                    target,
                )
                continue
            mounts.append(
                docker.types.Mount(
                    target,
                    source,
                    type="bind",
                    read_only=mapping.read_only,
                )
            )
            existing_targets.add(target)
            logger.log(
                25,
                "bioinfoflow mount added :: %s -> %s (ro=%s)",
                source,
                target,
                mapping.read_only,
            )

        return mounts

    def host_path(self, container_path: str, inputs_only: bool = False) -> str | None:
        """Resolve output File paths that fall under the platform's rw mounts.

        miniwdl's stock `host_path` (see `WDL/runtime/task_container.py`)
        raises `OutputError` on any declared output whose container path is
        not under the task's `/mnt/miniwdl_task_container/work` directory.
        Production WDLs such as Deaf_20 declare outputs like
        `File sample = "${outdir}/Sample.info"` where `outdir` is our
        identity-mounted per-run `results/` directory — always outside
        miniwdl's work dir, so always rejected by the default check.

        Because the platform is the party that mounted `results/` rw in the
        first place (see `configured_run_mounts`), paths under it are
        legitimate outputs. We short-circuit the check only for paths under
        a rw mount that the platform itself declared; anything else falls
        through to miniwdl's original validation so the security guard
        against `/etc/passwd`-style escapes stays intact.
        """
        if not inputs_only and os.path.isabs(container_path):
            is_dir_ref = container_path.endswith("/")
            bare = Path(container_path.rstrip("/"))
            for mapping in configured_run_mounts(self.host_dir):
                if mapping.read_only:
                    continue
                try:
                    bare.relative_to(mapping.container_root)
                except ValueError:
                    continue
                # Identity mount: container path == host path.
                if is_dir_ref:
                    return f"{bare}/" if bare.is_dir() else None
                return str(bare) if bare.is_file() else None
        return super().host_path(container_path, inputs_only=inputs_only)
