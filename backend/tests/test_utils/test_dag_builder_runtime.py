from __future__ import annotations

from app.utils.dag_builder import create_runtime_node, infer_runtime_edge


def test_create_runtime_node_marks_runtime_source():
    dag = {"nodes": [], "edges": []}

    node = create_runtime_node("nf-core/viralrecon:FASTQC (sample1)", "running", dag)

    assert node["id"] == "fastqc"
    assert node["data"]["label"] == "FASTQC"
    assert node["data"]["displayLabel"] == "FASTQC"
    assert node["data"]["status"] == "running"
    assert node["data"]["source"] == "runtime"


def test_infer_runtime_edge_appends_linear_edge():
    dag = {
        "nodes": [
            create_runtime_node("FASTQC", "success", {"nodes": [], "edges": []}),
            create_runtime_node("ALIGNMENT", "running", {"nodes": [{}], "edges": []}),
        ],
        "edges": [],
    }

    infer_runtime_edge(dag, "alignment")

    assert dag["edges"] == [
        {
            "id": "e_fastqc_alignment",
            "source": "fastqc",
            "target": "alignment",
            "animated": True,
        }
    ]
