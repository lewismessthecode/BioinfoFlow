from __future__ import annotations

from app.services.dag_parser import DagParser


def test_parse_dot_file_returns_empty_dag_for_missing_file(tmp_path):
    parser = DagParser()

    assert parser.parse_dot_file(tmp_path / "missing.dot") == {"nodes": [], "edges": []}


def test_parse_dot_file_cleans_labels_and_uses_schema_task_metadata(tmp_path):
    dot_path = tmp_path / "dag.dot"
    dot_path.write_text(
        'digraph {\n'
        '  p0 [label="nf-core/viralrecon:FASTQC (sample1)"]\n'
        '  p1 [label="MULTIQC"]\n'
        "  p0 -> p1\n"
        "}\n",
        encoding="utf-8",
    )
    schema = {
        "tasks": [
            {"name": "FASTQC", "inputs": ["reads"], "outputs": ["report"]},
            {"name": "MULTIQC", "inputs": ["report"], "outputs": ["html"]},
        ]
    }

    parser = DagParser()
    dag = parser.parse_dot_file(dot_path, schema=schema)

    assert [node["id"] for node in dag["nodes"]] == ["fastqc", "multiqc"]
    assert dag["nodes"][0]["data"]["inputs"] == {"reads": "reads"}
    assert dag["edges"] == [
        {
            "id": "e_fastqc_multiqc",
            "source": "fastqc",
            "target": "multiqc",
            "animated": False,
        }
    ]


def test_update_node_status_updates_normalized_process_name():
    dag = {
        "nodes": [
            {
                "id": "reads_stats",
                "type": "pipeline",
                "position": {"x": 0, "y": 0},
                "data": {"label": "READS_STATS", "status": "pending"},
            }
        ],
        "edges": [],
    }

    parser = DagParser()
    updated = parser.update_node_status(dag, "READS_STATS (sample1)", "running")

    assert updated["nodes"][0]["data"]["status"] == "running"


def test_update_edge_animations_only_animates_edges_from_running_sources():
    dag = {
        "nodes": [
            {
                "id": "fastqc",
                "type": "pipeline",
                "position": {"x": 0, "y": 0},
                "data": {"label": "FASTQC", "status": "success"},
            },
            {
                "id": "multiqc",
                "type": "pipeline",
                "position": {"x": 200, "y": 0},
                "data": {"label": "MULTIQC", "status": "running"},
            },
        ],
        "edges": [
            {
                "id": "e_fastqc_multiqc",
                "source": "fastqc",
                "target": "multiqc",
                "animated": False,
            }
        ],
    }

    updated = DagParser.update_edge_animations(dag)

    assert updated["edges"][0]["animated"] is False

