from __future__ import annotations

from app.utils.dag_matcher import DagMatcher


def _dag_nodes() -> list[dict]:
    return [
        {
            "id": "fastqc",
            "data": {"label": "FASTQC", "displayLabel": "FASTQC"},
        },
        {
            "id": "alignment",
            "data": {"label": "ALIGNMENT", "displayLabel": "ALIGNMENT"},
        },
    ]


def test_dag_matcher_matches_exact_id():
    assert DagMatcher(_dag_nodes()).match("FASTQC") == "fastqc"


def test_dag_matcher_matches_cleaned_label():
    assert DagMatcher(_dag_nodes()).match("FASTQC (sample1)") == "fastqc"


def test_dag_matcher_matches_suffix_name():
    assert DagMatcher(_dag_nodes()).match("workflow:sample:ALIGNMENT") == "alignment"


def test_dag_matcher_returns_none_when_no_match():
    assert DagMatcher(_dag_nodes()).match("UNKNOWN") is None
