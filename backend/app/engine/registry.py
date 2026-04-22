from __future__ import annotations

from app.engine.adapter import EngineAdapter
from app.engine.adapters.nextflow import NextflowAdapter
from app.engine.adapters.wdl import WDLAdapter

_ADAPTERS: dict[str, type[EngineAdapter]] = {}


def register_adapter(engine: str, cls: type[EngineAdapter]) -> None:
    _ADAPTERS[str(engine).strip().lower()] = cls


def get_adapter(engine: str) -> EngineAdapter:
    normalized = str(engine).strip().lower()
    cls = _ADAPTERS.get(normalized)
    if cls is None:
        raise ValueError(f"Unknown engine: {engine}")
    return cls()


register_adapter("nextflow", NextflowAdapter)
register_adapter("wdl", WDLAdapter)
