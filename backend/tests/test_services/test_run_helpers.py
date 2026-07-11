from __future__ import annotations

import re

import pytest

from app.services.run_helpers import generate_run_id, is_path_like_key


def test_generate_run_id_uses_128_bits_of_entropy():
    run_id = generate_run_id()

    assert re.fullmatch(r"run_[0-9a-f]{32}", run_id)


@pytest.mark.parametrize(
    "key",
    ["outdir", "OUTPUT_DIR", "publish_dir", "WORK_DIR"],
)
def test_managed_run_directory_names_are_not_path_like(key):
    assert is_path_like_key(key) is False


def test_ordinary_input_directory_name_remains_path_like():
    assert is_path_like_key("input_dir") is True
