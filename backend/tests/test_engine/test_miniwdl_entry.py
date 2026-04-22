"""Importing the miniwdl subprocess entry module must register our container
backend, regardless of whether `importlib.metadata` entry-point discovery is
working for the `miniwdl.plugin.container_backend` group.

Guarding this with a unit test catches the silent-fallback regression where
production miniwdl runs the stock SwarmContainer and loses the identity-mount
for `/srv/bioinfoflow/sources/deliveries`, which surfaces as a cryptic
"read sample list error" inside the Perl preparation step.
"""

from __future__ import annotations

import importlib


def test_miniwdl_entry_registers_bioinfoflow_container_backend():
    # Force a fresh import to guarantee the module-level setdefault runs even
    # if other tests already imported the module earlier in the session.
    module = importlib.reload(
        importlib.import_module("app.engine._miniwdl_entry"),
    )

    from WDL.runtime.task_container import _backends

    from app.engine.miniwdl_container_backend import BioinfoflowSwarmContainer

    assert module is not None
    assert _backends.get("bioinfoflow_docker_swarm") is BioinfoflowSwarmContainer
    # Stock docker_swarm must also still be registered — miniwdl's default
    # resolution path depends on it being present.
    assert "docker_swarm" in _backends
