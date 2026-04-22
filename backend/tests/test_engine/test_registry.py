from __future__ import annotations

import pytest

from app.engine.adapters.nextflow import NextflowAdapter
from app.engine.adapters.wdl import WDLAdapter
from app.engine.registry import get_adapter


def test_registry_returns_registered_engine_adapters():
    assert isinstance(get_adapter("nextflow"), NextflowAdapter)
    assert isinstance(get_adapter("wdl"), WDLAdapter)


def test_registry_raises_for_unknown_engine():
    with pytest.raises(ValueError, match="Unknown engine: snakemake"):
        get_adapter("snakemake")
