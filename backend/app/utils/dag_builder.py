"""DAG utilities for building canonical React Flow data structures."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

NODE_X_SPACING = 220
NODE_Y_SPACING = 140
NODE_X_OFFSET = 180
NODE_Y_OFFSET = 48


def clean_process_label(label: str) -> str:
    """Clean a process label by stripping workflow prefix and sample info.

    Examples:
        "nf-core/viralrecon:FASTQC (sample1)" -> "FASTQC"
        "MULTIQC" -> "MULTIQC"
        "FASTQC (sample1)" -> "FASTQC"
    """
    # Remove workflow prefix like "nf-core/viralrecon:"
    if ":" in label:
        label = label.split(":")[-1]
    # Remove sample info in parentheses
    if "(" in label:
        label = label.split("(")[0]
    return label.strip()


def normalize_dag_id(name: str) -> str:
    """Normalize a task/process name to a stable DAG node identifier."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", name.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized.lower()


def _task_metadata(task: dict[str, Any], status: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": task["name"],
        "displayLabel": task["name"],
        "status": status,
        "inputs": {value: value for value in task.get("inputs", [])},
        "outputs": {value: value for value in task.get("outputs", [])},
    }
    container = task.get("container")
    if container:
        data["container"] = container
    return data


def _normalize_tasks(
    tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    seen: set[str] = set()
    normalized_tasks: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}

    for task in tasks:
        name = str(task["name"]).strip()
        if not name:
            continue
        task_id = normalize_dag_id(name)
        if task_id in seen:
            continue
        seen.add(task_id)
        name_to_id[name] = task_id
        normalized_tasks.append(
            {
                "id": task_id,
                "name": name,
                "inputs": list(task.get("inputs", [])),
                "outputs": list(task.get("outputs", [])),
                "container": task.get("container"),
            }
        )

    return normalized_tasks, name_to_id


def _normalize_dependencies(
    dependencies: list[dict[str, Any]],
    known_ids: set[str],
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for dep in dependencies:
        source = normalize_dag_id(str(dep.get("source", "")))
        target = normalize_dag_id(str(dep.get("target", "")))
        if not source or not target or source == target:
            continue
        if source not in known_ids or target not in known_ids:
            continue
        pair = (source, target)
        if pair in seen:
            continue
        seen.add(pair)
        edges.append({"source": source, "target": target})

    return edges


def _topological_layers(
    task_ids: list[str], edges: list[dict[str, str]]
) -> dict[str, int]:
    children: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {task_id: 0 for task_id in task_ids}

    for edge in edges:
        children[edge["source"]].append(edge["target"])
        indegree[edge["target"]] = indegree.get(edge["target"], 0) + 1

    queue: deque[str] = deque(
        [task_id for task_id in task_ids if indegree[task_id] == 0]
    )
    depth: dict[str, int] = {task_id: 0 for task_id in task_ids}

    while queue:
        current = queue.popleft()
        current_depth = depth.get(current, 0)
        for child in children.get(current, []):
            depth[child] = max(depth.get(child, 0), current_depth + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    return depth


def _layout_positions(
    task_ids: list[str], edges: list[dict[str, str]]
) -> dict[str, dict[str, float]]:
    depths = _topological_layers(task_ids, edges)
    depth_groups: dict[int, list[str]] = defaultdict(list)

    for task_id in task_ids:
        depth_groups[depths.get(task_id, 0)].append(task_id)

    positions: dict[str, dict[str, float]] = {}
    for depth in sorted(depth_groups):
        names = depth_groups[depth]
        x_offset = -((len(names) - 1) * NODE_X_SPACING) / 2
        for index, name in enumerate(names):
            positions[name] = {
                "x": NODE_X_OFFSET + x_offset + index * NODE_X_SPACING,
                "y": NODE_Y_OFFSET + depth * NODE_Y_SPACING,
            }
    return positions


def build_canonical_dag(
    tasks: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    *,
    statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a canonical DAG from task metadata and dependencies."""
    normalized_tasks, _ = _normalize_tasks(tasks)
    if not normalized_tasks:
        return {"nodes": [], "edges": []}

    known_ids = {task["id"] for task in normalized_tasks}
    normalized_dependencies = _normalize_dependencies(dependencies, known_ids)
    positions = _layout_positions(
        [task["id"] for task in normalized_tasks], normalized_dependencies
    )
    statuses = statuses or {}

    nodes = [
        {
            "id": task["id"],
            "type": "pipeline",
            "position": positions[task["id"]],
            "data": _task_metadata(task, statuses.get(task["id"], "pending")),
        }
        for task in normalized_tasks
    ]
    edges = [
        {
            "id": f"e_{edge['source']}_{edge['target']}",
            "source": edge["source"],
            "target": edge["target"],
            "animated": False,
        }
        for edge in normalized_dependencies
    ]
    return {"nodes": nodes, "edges": edges}


def build_dag_from_schema(
    schema: dict[str, Any],
    *,
    statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert schema_json to canonical React Flow DAG format."""
    tasks = schema.get("tasks", [])
    dependencies = schema.get("dependencies", [])
    return build_canonical_dag(tasks, dependencies, statuses=statuses)


def create_runtime_node(
    task_name: str,
    status: str,
    existing_dag: dict[str, Any],
) -> dict[str, Any]:
    """Create a runtime-only node when a task event has no schema match."""
    label = clean_process_label(task_name)
    node_id = normalize_dag_id(label)
    y = len(existing_dag.get("nodes", [])) * NODE_Y_SPACING + NODE_Y_OFFSET
    return {
        "id": node_id,
        "type": "pipeline",
        "position": {"x": NODE_X_OFFSET, "y": y},
        "data": {
            "label": label,
            "displayLabel": label,
            "status": status,
            "source": "runtime",
            "inputs": {},
            "outputs": {},
        },
    }


def infer_runtime_edge(dag: dict[str, Any], new_node_id: str) -> None:
    """Infer a simple sequential edge for runtime-discovered nodes."""
    nodes = dag.get("nodes", [])
    if len(nodes) < 2:
        return

    previous_node = nodes[-2]
    previous_id = previous_node.get("id")
    if not isinstance(previous_id, str) or not previous_id:
        return

    edge_id = f"e_{previous_id}_{new_node_id}"
    if any(edge.get("id") == edge_id for edge in dag.get("edges", [])):
        return

    dag.setdefault("edges", []).append(
        {
            "id": edge_id,
            "source": previous_id,
            "target": new_node_id,
            "animated": True,
        }
    )
