from __future__ import annotations

import importlib
import importlib.util
import re

import pytest

from app.services.run_helpers import generate_run_id, is_path_like_key


def test_generate_run_id_uses_128_bits_of_entropy():
    run_id = generate_run_id()

    assert re.fullmatch(r"run_[0-9a-f]{32}", run_id)


def test_managed_run_directory_policy_has_exact_immutable_key_set():
    spec = importlib.util.find_spec("app.services.run_input_policy")
    assert spec is not None, "shared managed run-directory policy is missing"
    policy = importlib.import_module("app.services.run_input_policy")

    expected = frozenset({"outdir", "output_dir", "publish_dir", "work_dir"})
    assert isinstance(policy.MANAGED_RUN_DIRECTORY_NAMES, frozenset)
    assert policy.MANAGED_RUN_DIRECTORY_NAMES == expected
    assert all(policy.is_managed_run_directory_name(name.upper()) for name in expected)
    assert policy.is_managed_run_directory_name("workflow.outdir") is False
    assert policy.is_managed_run_directory_name(" outdir ") is False
    assert policy.is_managed_run_directory_name("results_dir") is False


@pytest.mark.parametrize(
    "key",
    ["outdir", "OUTPUT_DIR", "publish_dir", "WORK_DIR"],
)
def test_managed_run_directory_names_are_not_path_like(key):
    assert is_path_like_key(key) is False


def test_ordinary_input_directory_name_remains_path_like():
    assert is_path_like_key("input_dir") is True
