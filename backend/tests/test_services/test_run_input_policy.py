from __future__ import annotations

from app.services.run_input_policy import (
    MANAGED_RUN_DIRECTORY_NAMES,
    is_managed_run_directory_name,
)


def test_managed_run_directory_policy_has_exact_immutable_key_set():
    expected = frozenset({"outdir", "output_dir", "publish_dir", "work_dir"})

    assert isinstance(MANAGED_RUN_DIRECTORY_NAMES, frozenset)
    assert MANAGED_RUN_DIRECTORY_NAMES == expected
    assert all(is_managed_run_directory_name(name.upper()) for name in expected)
    assert is_managed_run_directory_name("workflow.outdir") is False
    assert is_managed_run_directory_name(" outdir ") is False
    assert is_managed_run_directory_name("results_dir") is False
