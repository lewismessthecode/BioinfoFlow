from __future__ import annotations

from app.services.dag_parser import DagParser
from app.utils.dag_builder import build_dag_from_schema


def _example_schema() -> dict:
    return {
        "tasks": [
            {
                "name": "FASTQC",
                "inputs": ["reads"],
                "outputs": ["report"],
                "container": "biocontainers/fastqc:0.12.1",
            },
            {
                "name": "ALIGNMENT",
                "inputs": ["reads", "reference"],
                "outputs": ["bam"],
                "container": "biocontainers/bwa:0.7.17",
            },
            {
                "name": "VARIANT_CALLING",
                "inputs": ["bam"],
                "outputs": ["vcf"],
                "container": "biocontainers/freebayes:1.3.7",
            },
        ],
        "dependencies": [
            {"source": "FASTQC", "target": "ALIGNMENT"},
            {"source": "ALIGNMENT", "target": "VARIANT_CALLING"},
        ],
    }


def test_build_dag_from_schema_returns_canonical_metadata() -> None:
    dag = build_dag_from_schema(_example_schema())

    assert [node["id"] for node in dag["nodes"]] == [
        "fastqc",
        "alignment",
        "variant_calling",
    ]
    assert [node["data"] for node in dag["nodes"]] == [
        {
            "label": "FASTQC",
            "displayLabel": "FASTQC",
            "status": "pending",
            "inputs": {"reads": "reads"},
            "outputs": {"report": "report"},
            "container": "biocontainers/fastqc:0.12.1",
        },
        {
            "label": "ALIGNMENT",
            "displayLabel": "ALIGNMENT",
            "status": "pending",
            "inputs": {"reads": "reads", "reference": "reference"},
            "outputs": {"bam": "bam"},
            "container": "biocontainers/bwa:0.7.17",
        },
        {
            "label": "VARIANT_CALLING",
            "displayLabel": "VARIANT_CALLING",
            "status": "pending",
            "inputs": {"bam": "bam"},
            "outputs": {"vcf": "vcf"},
            "container": "biocontainers/freebayes:1.3.7",
        },
    ]
    assert dag["edges"] == [
        {
            "id": "e_fastqc_alignment",
            "source": "fastqc",
            "target": "alignment",
            "animated": False,
        },
        {
            "id": "e_alignment_variant_calling",
            "source": "alignment",
            "target": "variant_calling",
            "animated": False,
        },
    ]
    assert all(isinstance(node["position"]["x"], (int, float)) for node in dag["nodes"])
    assert all(isinstance(node["position"]["y"], (int, float)) for node in dag["nodes"])


def test_parse_dot_file_matches_canonical_shape_when_schema_is_available(
    tmp_path,
) -> None:
    dot_path = tmp_path / "dag.dot"
    dot_path.write_text(
        """
        digraph G {
          p0 [label="FASTQC"]
          p1 [label="ALIGNMENT"]
          p2 [label="VARIANT_CALLING"]
          p0 -> p1
          p1 -> p2
        }
        """,
        encoding="utf-8",
    )

    dag = DagParser().parse_dot_file(dot_path, schema=_example_schema())

    assert [node["id"] for node in dag["nodes"]] == [
        "fastqc",
        "alignment",
        "variant_calling",
    ]
    assert [node["data"] for node in dag["nodes"]] == [
        {
            "label": "FASTQC",
            "displayLabel": "FASTQC",
            "status": "pending",
            "inputs": {"reads": "reads"},
            "outputs": {"report": "report"},
            "container": "biocontainers/fastqc:0.12.1",
        },
        {
            "label": "ALIGNMENT",
            "displayLabel": "ALIGNMENT",
            "status": "pending",
            "inputs": {"reads": "reads", "reference": "reference"},
            "outputs": {"bam": "bam"},
            "container": "biocontainers/bwa:0.7.17",
        },
        {
            "label": "VARIANT_CALLING",
            "displayLabel": "VARIANT_CALLING",
            "status": "pending",
            "inputs": {"bam": "bam"},
            "outputs": {"vcf": "vcf"},
            "container": "biocontainers/freebayes:1.3.7",
        },
    ]
    assert dag["edges"] == [
        {
            "id": "e_fastqc_alignment",
            "source": "fastqc",
            "target": "alignment",
            "animated": False,
        },
        {
            "id": "e_alignment_variant_calling",
            "source": "alignment",
            "target": "variant_calling",
            "animated": False,
        },
    ]
