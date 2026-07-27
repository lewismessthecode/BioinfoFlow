from __future__ import annotations

import re

import pytest

from app.utils.project_directory_names import (
    MAX_PROJECT_DIRECTORY_LENGTH,
    normalize_project_directory_name,
    project_directory_candidate,
)


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        ("BioinfoFlow Demo", "bioinfoflow-demo"),
        ("测试", "ce-shi"),
        ("肿瘤 RNA 分析", "zhong-liu-rna-fen-xi"),
        ("  Demo___Project  ", "demo-project"),
        ("Café", "cafe"),
        ("😀🚀", "project"),
    ],
)
def test_normalize_project_directory_name_creates_readable_ascii_kebab_case(
    project_name: str,
    expected: str,
) -> None:
    result = normalize_project_directory_name(project_name)

    assert result == expected
    assert re.fullmatch(r"[a-z0-9-]+", result)


def test_normalized_base_name_is_limited_to_100_characters() -> None:
    result = normalize_project_directory_name("a" * 101)

    assert result == "a" * MAX_PROJECT_DIRECTORY_LENGTH
    assert len(result) == MAX_PROJECT_DIRECTORY_LENGTH


@pytest.mark.parametrize(
    "reserved_name",
    [
        "CON",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    ],
)
def test_normalize_project_directory_name_avoids_windows_reserved_names(
    reserved_name: str,
) -> None:
    normalized = reserved_name.lower()

    assert normalize_project_directory_name(reserved_name) == f"project-{normalized}"


@pytest.mark.parametrize(
    ("ordinal", "suffix_length"),
    [(2, 2), (10000, 6)],
)
def test_project_directory_candidate_reserves_space_for_its_suffix(
    ordinal: int,
    suffix_length: int,
) -> None:
    result = project_directory_candidate("a" * 100, ordinal)

    assert result.endswith(f"-{ordinal}")
    assert len(result) == MAX_PROJECT_DIRECTORY_LENGTH
    assert (
        result == "a" * (MAX_PROJECT_DIRECTORY_LENGTH - suffix_length) + f"-{ordinal}"
    )


def test_project_directory_candidate_uses_unsuffixed_name_for_first_ordinal() -> None:
    assert project_directory_candidate("BioinfoFlow Demo", 1) == "bioinfoflow-demo"


def test_project_directory_candidate_rejects_ordinals_below_one() -> None:
    with pytest.raises(ValueError, match="ordinal"):
        project_directory_candidate("BioinfoFlow Demo", 0)
