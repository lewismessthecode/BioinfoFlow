from __future__ import annotations

import re

import pytest

from app.services import run_helpers
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


@pytest.mark.parametrize(
    "pattern",
    [
        "reads/*.fastq.gz",
        "reads/sample_[12]?.fastq.gz",
        "literal,comma",
    ],
)
def test_expand_brace_glob_patterns_passes_through_patterns_without_braces(pattern):
    assert run_helpers.expand_brace_glob_patterns(pattern) == [pattern]


def test_expand_brace_glob_patterns_expands_one_group_and_strips_options():
    assert run_helpers.expand_brace_glob_patterns(
        "reads/*_{ R1, ,R2 }.fastq.gz"
    ) == [
        "reads/*_R1.fastq.gz",
        "reads/*_R2.fastq.gz",
    ]


def test_expand_brace_glob_patterns_expands_multiple_groups_in_depth_first_order():
    assert run_helpers.expand_brace_glob_patterns("sample_{A,B}_{1,2}.txt") == [
        "sample_A_1.txt",
        "sample_A_2.txt",
        "sample_B_1.txt",
        "sample_B_2.txt",
    ]


def test_expand_brace_glob_patterns_preserves_current_nested_group_order():
    assert run_helpers.expand_brace_glob_patterns("sample_{A,{B,C}}.txt") == [
        "sample_A.txt",
        "sample_B.txt",
        "sample_A.txt",
        "sample_C.txt",
    ]


@pytest.mark.parametrize(
    "pattern",
    [
        "reads/{}.fastq.gz",
        "reads/{,}.fastq.gz",
        "reads/{   }.fastq.gz",
        "reads/{R1,R2.fastq.gz",
        "reads/R1,R2}.fastq.gz",
    ],
)
def test_expand_brace_glob_patterns_passes_through_empty_or_unbalanced_groups(
    pattern,
):
    assert run_helpers.expand_brace_glob_patterns(pattern) == [pattern]


def test_expand_brace_glob_patterns_expands_valid_group_inside_malformed_outer_group():
    assert run_helpers.expand_brace_glob_patterns("sample_{A,{B,C}.txt") == [
        "sample_{A,B.txt",
        "sample_{A,C.txt",
    ]


def test_expand_brace_glob_patterns_leaves_unmatched_closing_brace_literal():
    assert run_helpers.expand_brace_glob_patterns("sample_{A,B}}.txt") == [
        "sample_A}.txt",
        "sample_B}.txt",
    ]
