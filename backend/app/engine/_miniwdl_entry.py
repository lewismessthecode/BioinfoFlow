"""Subprocess entrypoint that explicitly registers the bioinfoflow swarm backend.

miniwdl discovers container backends via `importlib.metadata` entry points.
When the subprocess's Python environment is missing our package's dist-info
(or the entry point was never materialized by the installer), miniwdl silently
falls back to the stock `SwarmContainer` — our `prepare_mounts` override
never runs, and task containers lose the `/srv/bioinfoflow/sources/deliveries`
identity mount. The failure mode is indistinguishable from "file not found"
inside the Perl script that reads the sample sheet.

Invoking this module as the miniwdl CLI (`python -m app.engine._miniwdl_entry run ...`)
pre-populates `WDL.runtime.task_container._backends` from our own imports,
bypassing entry-point discovery entirely.
"""

from __future__ import annotations

import os
import sys

from WDL.CLI import main
from WDL.runtime.backend.docker_swarm import SwarmContainer
from WDL.runtime.task_container import _backends

from app.engine.miniwdl_container_backend import BioinfoflowSwarmContainer

_backends["docker_swarm"] = SwarmContainer
_backends["bioinfoflow_docker_swarm"] = BioinfoflowSwarmContainer


# Loud startup marker — this line is the first thing in the subprocess's
# stderr, well before miniwdl's own NOTICE output. Seeing it in run logs
# proves the adapter actually invoked us; not seeing it means the deployed
# image still runs the raw `miniwdl` binary or the module failed to import.
sys.stderr.write(
    "[BIOINFOFLOW] miniwdl subprocess entry loaded "
    f"(pid={os.getpid()}, python={sys.executable}, "
    f"backends={sorted(_backends)})\n"
)
sys.stderr.flush()


if __name__ == "__main__":
    sys.exit(main())
