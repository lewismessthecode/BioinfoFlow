"""Integration tests for BGI Deaf_20 WDL parsing and DAG extraction.

Verifies that the deaf_20.wdl file integrates correctly with bioinfoflow's
WDL parsing pipeline: all 5 tasks are discovered, and the expected dependency
edges are extracted (including scatter-level and workflow-scope references).

Tests both the WorkflowValidator (miniwdl + regex fallback) and the
WDLAdapter.extract_schema code paths.
"""

from __future__ import annotations

import pytest

from app.engine.adapters.wdl import WDLAdapter
from app.services.workflow_validator import WorkflowValidator
from tests.test_services.test_workflow_validator import DEAF_20_WDL

EXPECTED_TASKS = {"PREPARATION", "SPLIT", "FILTER", "ALIGN", "RESULT"}

# The 6 expected DAG edges:
# 1. PREPARATION -> SPLIT   (via scatter over read_tsv(PREPARATION.PREPARATION_sample_info_dedup))
# 2. PREPARATION -> FILTER  (via scatter over read_tsv(PREPARATION.PREPARATION_sample_info))
# 3. PREPARATION -> ALIGN   (via scatter over read_tsv(PREPARATION.PREPARATION_sample_info))
# 4. SPLIT -> FILTER        (via SPLIT_FINISHED=SPLIT.SPLIT_FINISHED in call inputs)
# 5. FILTER -> ALIGN        (via FILTER_FINISHED=FILTER.FILTER_FINISHED in call inputs)
# 6. ALIGN -> RESULT        (via ALIGN_FINISHED=ALIGN.ALIGN_FINISHED in call inputs)
EXPECTED_EDGES = {
    ("PREPARATION", "SPLIT"),
    ("PREPARATION", "FILTER"),
    ("PREPARATION", "ALIGN"),
    ("SPLIT", "FILTER"),
    ("FILTER", "ALIGN"),
    ("ALIGN", "RESULT"),
}


@pytest.fixture
def deaf20_content() -> str:
    """Return a production-shaped Deaf_20 fixture without relying on demo bundles."""
    return DEAF_20_WDL


@pytest.fixture
def validator() -> WorkflowValidator:
    return WorkflowValidator()


class TestDeaf20WdlParsing:
    """Verify deaf_20.wdl is parseable by the WDL validator."""

    def test_workflow_output_forwards_result_task_output(self, deaf20_content):
        assert "File zip_result = RESULT.zip_result" in deaf20_content

    def test_result_task_exports_zip_artifact(self, deaf20_content):
        # The output declaration uses the literal `Result.zip` name. The
        # command block must include a step that restores that name after
        # `rename.pl` moves the artifact to `{slide}_Result.zip` —
        # otherwise miniwdl's post-task File validation cannot resolve it.
        # We can't use miniwdl's `glob()` here because miniwdl restricts
        # glob patterns to be relative to the task work dir, not `${outdir}`.
        assert (
            'File zip_result = "${outdir}/output/pipeline/Result.zip"' in deaf20_content
        )
        assert "cp ${outdir}/output/pipeline/*_Result.zip" in deaf20_content

    def test_tasks_use_docker_runtime_attribute(self, deaf20_content):
        assert 'docker: "deaf:V2.0.9.9"' in deaf20_content
        assert 'image: "deaf:V2.0.9.9"' not in deaf20_content

    def test_basic_validation_passes(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.valid, f"Validation failed: {[e.message for e in result.errors]}"

    def test_workflow_name(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.workflow_name == "Deaf_20"

    def test_version_detected(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.version == "1.0"


class TestDeaf20TaskDiscovery:
    """Verify all 5 tasks are discovered."""

    def test_all_five_tasks_found(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.valid
        found_tasks = {t.name for t in result.tasks}
        assert found_tasks == EXPECTED_TASKS

    def test_task_containers_extracted(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        containers = {t.name: t.container for t in result.tasks}
        # All tasks in this WDL use the same deaf:V2.0.9.9 image
        # (miniwdl str() may include surrounding quotes)
        for task_name in EXPECTED_TASKS:
            assert containers[task_name] is not None
            assert "deaf:V2.0.9.9" in containers[task_name]


class TestDeaf20DependencyExtraction:
    """Verify all 6 expected DAG edges are extracted.

    The deaf_20.wdl uses patterns that go beyond simple call-input references:
    - Scatter over read_tsv(PREPARATION.xxx): PREPARATION -> SPLIT/FILTER/ALIGN
    - Direct call-input refs: SPLIT -> FILTER, FILTER -> ALIGN, ALIGN -> RESULT
    """

    def test_finds_all_six_edges(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.valid
        actual_edges = {(d.source, d.target) for d in result.dependencies}
        assert actual_edges == EXPECTED_EDGES, (
            f"Missing edges: {EXPECTED_EDGES - actual_edges}, "
            f"Extra edges: {actual_edges - EXPECTED_EDGES}"
        )

    def test_preparation_to_split_via_read_tsv(self, validator, deaf20_content):
        """PREPARATION -> SPLIT via read_tsv(PREPARATION.PREPARATION_sample_info_dedup)."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("PREPARATION", "SPLIT") in edges

    def test_preparation_to_filter_via_read_tsv(self, validator, deaf20_content):
        """PREPARATION -> FILTER via read_tsv(PREPARATION.PREPARATION_sample_info)."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("PREPARATION", "FILTER") in edges

    def test_preparation_to_align_via_read_tsv(self, validator, deaf20_content):
        """PREPARATION -> ALIGN via read_tsv(PREPARATION.PREPARATION_sample_info)."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("PREPARATION", "ALIGN") in edges

    def test_split_to_filter_via_barrier(self, validator, deaf20_content):
        """SPLIT -> FILTER via SPLIT_FINISHED barrier."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("SPLIT", "FILTER") in edges

    def test_filter_to_align_via_barrier(self, validator, deaf20_content):
        """FILTER -> ALIGN via FILTER_FINISHED barrier."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("FILTER", "ALIGN") in edges

    def test_align_to_result(self, validator, deaf20_content):
        """ALIGN -> RESULT via ALIGN_FINISHED + ALIGN.ALIGN_stat."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("ALIGN", "RESULT") in edges

    def test_no_filter_to_result_edge(self, validator, deaf20_content):
        """FILTER -> RESULT does not exist — RESULT only references ALIGN."""
        result = validator.validate(deaf20_content, "wdl")
        edges = {(d.source, d.target) for d in result.dependencies}
        assert ("FILTER", "RESULT") not in edges


class TestDeaf20WorkflowScopeRefExtraction:
    """Verify that workflow-scope task references are detected.

    These are references like:
      Array[Array[String]] split_samples = read_tsv(PREPARATION.xxx)
      Array[String] SPLIT_FINISHED = SPLIT.SPLIT_FINISHED
    that appear at workflow scope (not inside call blocks).
    """

    def test_workflow_scope_refs_contribute_to_dag(self, validator, deaf20_content):
        """Workflow-scope refs should create edges to the next call that uses them."""
        result = validator.validate(deaf20_content, "wdl")
        assert result.valid
        edges = {(d.source, d.target) for d in result.dependencies}
        # The read_tsv(PREPARATION.xxx) feeds into scatter blocks that contain
        # call SPLIT, call FILTER, call ALIGN
        assert ("PREPARATION", "SPLIT") in edges
        assert ("PREPARATION", "FILTER") in edges
        assert ("PREPARATION", "ALIGN") in edges


class TestDeaf20NoDuplicateEdges:
    """Verify that duplicate edges are not emitted."""

    def test_no_duplicate_dependencies(self, validator, deaf20_content):
        result = validator.validate(deaf20_content, "wdl")
        assert result.valid
        edges = [(d.source, d.target) for d in result.dependencies]
        assert len(edges) == len(set(edges)), (
            f"Duplicate edges found: {[e for e in edges if edges.count(e) > 1]}"
        )


class TestDeaf20RegexFallback:
    """Verify the basic (regex) validation fallback produces the same results.

    The regex fallback is used when miniwdl is unavailable or when called
    from within an already-running async event loop.
    """

    def test_basic_fallback_finds_all_tasks(self, validator, deaf20_content):
        result = validator._validate_wdl_basic(deaf20_content, "deaf_20.wdl")
        assert result.valid
        found_tasks = {t.name for t in result.tasks}
        assert found_tasks == EXPECTED_TASKS

    def test_basic_fallback_finds_all_edges(self, validator, deaf20_content):
        result = validator._validate_wdl_basic(deaf20_content, "deaf_20.wdl")
        actual_edges = {(d.source, d.target) for d in result.dependencies}
        assert actual_edges == EXPECTED_EDGES, (
            f"Missing edges: {EXPECTED_EDGES - actual_edges}, "
            f"Extra edges: {actual_edges - EXPECTED_EDGES}"
        )

    def test_basic_fallback_no_duplicate_edges(self, validator, deaf20_content):
        result = validator._validate_wdl_basic(deaf20_content, "deaf_20.wdl")
        edges = [(d.source, d.target) for d in result.dependencies]
        assert len(edges) == len(set(edges))

    def test_basic_fallback_workflow_name(self, validator, deaf20_content):
        result = validator._validate_wdl_basic(deaf20_content, "deaf_20.wdl")
        assert result.workflow_name == "Deaf_20"


class TestDeaf20WdlAdapterExtractSchema:
    """Verify the WDLAdapter.extract_schema path also works with deaf_20.wdl.

    This is the code path used by the engine layer (as opposed to the
    WorkflowValidator used by the validation service).
    """

    @pytest.mark.asyncio
    async def test_adapter_extracts_schema(self, deaf20_content):
        adapter = WDLAdapter()
        schema = await adapter.extract_schema(
            None, content=deaf20_content, file_name="deaf_20.wdl"
        )
        assert schema is not None
        assert schema["workflow_name"] == "Deaf_20"

    @pytest.mark.asyncio
    async def test_adapter_finds_all_tasks(self, deaf20_content):
        adapter = WDLAdapter()
        schema = await adapter.extract_schema(
            None, content=deaf20_content, file_name="deaf_20.wdl"
        )
        assert schema is not None
        found_tasks = {t["name"] for t in schema["tasks"]}
        assert found_tasks == EXPECTED_TASKS

    @pytest.mark.asyncio
    async def test_adapter_finds_all_edges(self, deaf20_content):
        adapter = WDLAdapter()
        schema = await adapter.extract_schema(
            None, content=deaf20_content, file_name="deaf_20.wdl"
        )
        assert schema is not None
        actual_edges = {(d["source"], d["target"]) for d in schema["dependencies"]}
        assert actual_edges == EXPECTED_EDGES, (
            f"Missing edges: {EXPECTED_EDGES - actual_edges}, "
            f"Extra edges: {actual_edges - EXPECTED_EDGES}"
        )

    @pytest.mark.asyncio
    async def test_adapter_no_duplicate_edges(self, deaf20_content):
        adapter = WDLAdapter()
        schema = await adapter.extract_schema(
            None, content=deaf20_content, file_name="deaf_20.wdl"
        )
        assert schema is not None
        edges = [(d["source"], d["target"]) for d in schema["dependencies"]]
        assert len(edges) == len(set(edges))

    @pytest.mark.asyncio
    async def test_adapter_extracts_containers(self, deaf20_content):
        adapter = WDLAdapter()
        schema = await adapter.extract_schema(
            None, content=deaf20_content, file_name="deaf_20.wdl"
        )
        assert schema is not None
        containers = {t["name"]: t["container"] for t in schema["tasks"]}
        for task_name in EXPECTED_TASKS:
            assert containers[task_name] is not None
            assert "deaf:V2.0.9.9" in containers[task_name]
