from __future__ import annotations

from app.utils.dag_builder import clean_process_label, normalize_dag_id


class DagMatcher:
    def __init__(self, dag_nodes: list[dict]):
        self._nodes = {
            str(node.get("id")): node
            for node in dag_nodes
            if isinstance(node.get("id"), str)
        }

    def match(self, runtime_task_name: str | None) -> str | None:
        if not isinstance(runtime_task_name, str) or not runtime_task_name.strip():
            return None

        raw = runtime_task_name.strip()
        cleaned = clean_process_label(raw)
        target_id = normalize_dag_id(cleaned)

        if target_id in self._nodes:
            return target_id

        for node_id, node in self._nodes.items():
            if _matches_node_label(node, cleaned):
                return node_id

        for candidate in _suffix_candidates(raw):
            candidate_id = normalize_dag_id(candidate)
            if candidate_id in self._nodes:
                return candidate_id

        for node_id, node in self._nodes.items():
            if target_id and (target_id in node_id or node_id in target_id):
                return node_id
            if _label_contains(node, cleaned):
                return node_id

        return None


def _matches_node_label(node: dict, cleaned: str) -> bool:
    cleaned_lower = cleaned.lower()
    for label in _candidate_labels(node):
        if clean_process_label(label).lower() == cleaned_lower:
            return True
    return False


def _label_contains(node: dict, cleaned: str) -> bool:
    cleaned_lower = cleaned.lower()
    for label in _candidate_labels(node):
        normalized = clean_process_label(label).lower()
        if cleaned_lower in normalized or normalized in cleaned_lower:
            return True
    return False


def _candidate_labels(node: dict) -> list[str]:
    data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
    labels = []
    for key in ("label", "displayLabel"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            labels.append(value.strip())
    return labels


def _suffix_candidates(raw: str) -> list[str]:
    parts = [part.strip() for part in raw.split(":") if part.strip()]
    if len(parts) < 2:
        return []
    return [clean_process_label(part) for part in parts[1:]]
