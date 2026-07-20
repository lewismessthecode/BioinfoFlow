from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True, slots=True)
class DemoWorkflowContract:
    id: str
    name: str
    version: str
    engine: str
    source: str
    source_ref: str
    entrypoint_relpath: str
    bundle_kind: str
    marker: str
    runtime_image: str
    task_names: tuple[str, ...]

    def reserves(self, *, source: object, name: object, version: object) -> bool:
        return (
            _value(source) == self.source
            and str(name or "") == self.name
            and str(version or "") == self.version
        )

    def matches(self, workflow: object) -> bool:
        return (
            str(getattr(workflow, "id", "")) == self.id
            and str(getattr(workflow, "name", "")) == self.name
            and str(getattr(workflow, "version", "")) == self.version
            and _value(getattr(workflow, "engine", "")) == self.engine
            and _value(getattr(workflow, "source", "")) == self.source
            and str(getattr(workflow, "source_ref", "")) == self.source_ref
            and str(getattr(workflow, "entrypoint_relpath", ""))
            == self.entrypoint_relpath
            and str(getattr(workflow, "bundle_kind", "")) == self.bundle_kind
            and self.marker in str(getattr(workflow, "description", "") or "")
            and self.schema_uses_runtime_image(
                getattr(workflow, "schema_json", None)
            )
        )

    def schema_uses_runtime_image(self, schema_json: object) -> bool:
        if not isinstance(schema_json, dict):
            return False
        tasks = schema_json.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != len(self.task_names):
            return False
        return sorted(
            (str(task.get("name", "")), str(task.get("container", "")))
            for task in tasks
            if isinstance(task, dict)
        ) == sorted((name, self.runtime_image) for name in self.task_names)


def _value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


DEMO_WORKFLOW = DemoWorkflowContract(
    id=str(uuid5(NAMESPACE_URL, "bioinfoflow:quickstart-workflow:1.0.0")),
    name="bioinfoflow-quickstart",
    version="1.0.0",
    engine="wdl",
    source="local",
    source_ref="local",
    entrypoint_relpath="workflow.wdl",
    bundle_kind="local_bundle",
    marker="bioinfoflow.demo.quickstart.v1",
    runtime_image=(
        "alpine:3.20.3@sha256:"
        "1e42bbe2508154c9126d48c2b8a75420c3544343bf86fd041fb7527e017a4b4a"
    ),
    task_names=("summarize_reads", "render_report"),
)
