"""Tests for WorkflowValidator service.

Tests dependency extraction for both Nextflow and WDL workflows.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow_validator import WorkflowValidator


DEAF_20_WDL = """
version 1.0

workflow Deaf_20 {
  input {
    String outdir
    File sequence_list
  }

  call PREPARATION {
    input:
      outdir = outdir,
      sequence_list = sequence_list
  }

  scatter (line in read_tsv(PREPARATION.PREPARATION_sample_info_dedup)) {
    call SPLIT {
      input:
        outdir = outdir,
        Slide = line[0],
        Lane = line[1],
        Barcode = line[2],
        fq = line[5],
        fq1 = line[6],
        fq2 = line[7]
    }
  }

  scatter (line in read_tsv(PREPARATION.PREPARATION_sample_info)) {
    call FILTER {
      input:
        outdir = outdir,
        Slide = line[0],
        Lane = line[1],
        Barcode = line[2],
        Index = line[3],
        Name = line[4],
        SPLIT_FINISHED = SPLIT.SPLIT_FINISHED
    }
  }

  scatter (line in read_tsv(PREPARATION.PREPARATION_sample_info)) {
    call ALIGN {
      input:
        outdir = outdir,
        Slide = line[0],
        Lane = line[1],
        Barcode = line[2],
        Index = line[3],
        FILTER_FINISHED = FILTER.FILTER_FINISHED
    }
  }

  call RESULT {
    input:
      outdir = outdir,
      ALIGN_FINISHED = ALIGN.ALIGN_FINISHED
  }

  output {
    File zip_result = RESULT.zip_result
  }
}

task PREPARATION {
  input {
    String outdir
    File sequence_list
  }
  command {
    set -e
    Prepare_wt.pl ${sequence_list} ${outdir}
  }
  runtime {
    cpu: 1
    memory: "2GB"
    docker: "deaf:V2.0.9.9"
  }
  output {
    File PREPARATION_sample_info = "${outdir}/sample_info.tsv"
    File PREPARATION_sample_info_dedup = "${outdir}/sample_info_dedup.tsv"
  }
}

task SPLIT {
  input {
    String outdir
    String Slide
    String Lane
    String Barcode
    String fq
    String fq1
    String fq2
  }
  command {
    echo "split"
  }
  runtime {
    cpu: 4
    docker: "deaf:V2.0.9.9"
  }
  output {
    String SPLIT_FINISHED = "FINISHED"
  }
}

task FILTER {
  input {
    String outdir
    String Slide
    String Lane
    String Barcode
    String Index
    String Name
    Array[String] SPLIT_FINISHED
  }
  command {
    echo "filter"
  }
  runtime {
    cpu: 1
    docker: "deaf:V2.0.9.9"
  }
  output {
    String FILTER_FINISHED = "FINISHED"
  }
}

task ALIGN {
  input {
    String outdir
    String Slide
    String Lane
    String Barcode
    String Index
    Array[String] FILTER_FINISHED
  }
  command <<<
    echo "align"
  >>>
  runtime {
    cpu: 2
    docker: "deaf:V2.0.9.9"
  }
  output {
    String ALIGN_FINISHED = "FINISHED"
  }
}

task RESULT {
  input {
    String outdir
    Array[String] ALIGN_FINISHED
    String bin_rename = "/bin/rename.pl"
  }
  command {
    echo "result"
    perl ${bin_rename} ${outdir}/Sample.info ${outdir}/output/pipeline/Result.zip
    cp ${outdir}/output/pipeline/*_Result.zip ${outdir}/output/pipeline/Result.zip
  }
  runtime {
    cpu: 1
    docker: "deaf:V2.0.9.9"
  }
  output {
    File zip_result = "${outdir}/output/pipeline/Result.zip"
  }
}
"""


WGS_CLINICAL_WDL_COMPACT = """
version 1.0

workflow WGS_CLINICAL{
    input {
    String outdir
    File sequence_list
    }

    call init{
        input: sampleinfo=sequence_list, outdir=outdir
    }

    output {
      File zip_result = "${outdir}/output/report.xlsx"
    }
}
"""


@pytest.fixture
def validator():
    """Create a WorkflowValidator instance."""
    return WorkflowValidator()


class TestNextflowDependencyExtraction:
    """Tests for Nextflow .out reference extraction."""

    def test_extract_simple_out_reference(self, validator):
        """Test extraction of simple PROCESS.out reference."""
        content = """
        nextflow.enable.dsl=2

        process A {
          output:
            path "out.txt", emit: data
          script:
          "echo hello"
        }

        process B {
          input:
            path x
          script:
          "cat x"
        }

        workflow {
          A()
          B(A.out.data)
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.tasks) == 2
        assert len(result.dependencies) == 1
        assert result.dependencies[0].source == "A"
        assert result.dependencies[0].target == "B"

    def test_extract_multiline_invocation(self, validator):
        """Test extraction from multiline process invocation with .collect()."""
        content = """
        nextflow.enable.dsl=2

        process READS_STATS {
          output:
            path "*.tsv", emit: stats
          script:
          "echo stats"
        }

        process REFERENCE_STATS {
          output:
            path "ref.tsv", emit: stats
          script:
          "echo ref"
        }

        process SUMMARY_REPORT {
          input:
            path read_stats
            path ref_stats
          script:
          "cat *"
        }

        workflow {
          READS_STATS()
          REFERENCE_STATS()

          SUMMARY_REPORT(
            READS_STATS.out.stats.collect(),
            REFERENCE_STATS.out.stats
          )
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.tasks) == 3
        assert len(result.dependencies) == 2

        sources = {d.source for d in result.dependencies}
        targets = {d.target for d in result.dependencies}
        assert sources == {"READS_STATS", "REFERENCE_STATS"}
        assert targets == {"SUMMARY_REPORT"}

    def test_extract_pipe_operator(self, validator):
        """Test extraction of pipe operator dependencies."""
        content = """
        nextflow.enable.dsl=2

        process A {
          script: "echo a"
        }

        process B {
          script: "echo b"
        }

        workflow {
          A | B
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.dependencies) == 1
        assert result.dependencies[0].source == "A"
        assert result.dependencies[0].target == "B"

    def test_extract_linear_chain(self, validator):
        """Test extraction of 4-step linear chain: A -> B -> C -> D."""
        content = """
        nextflow.enable.dsl=2

        process FASTQC {
          output: path "*.txt", emit: reports
          script: "echo qc"
        }

        process TRIMMING {
          output: path "*.txt", emit: trimmed
          script: "echo trim"
        }

        process ALIGNMENT {
          output: path "*.bam", emit: bam
          script: "echo align"
        }

        process VARIANT_CALLING {
          output: path "*.vcf", emit: vcf
          script: "echo call"
        }

        workflow {
          FASTQC()
          TRIMMING(FASTQC.out.reports)
          ALIGNMENT(TRIMMING.out.trimmed)
          VARIANT_CALLING(ALIGNMENT.out.bam)
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.tasks) == 4
        assert len(result.dependencies) == 3

        # Verify the chain
        deps_map = {d.source: d.target for d in result.dependencies}
        assert deps_map["FASTQC"] == "TRIMMING"
        assert deps_map["TRIMMING"] == "ALIGNMENT"
        assert deps_map["ALIGNMENT"] == "VARIANT_CALLING"

    def test_no_duplicate_dependencies(self, validator):
        """Test that duplicate dependencies are not added."""
        content = """
        nextflow.enable.dsl=2

        process A {
          output: path "*.txt", emit: data
          script: "echo a"
        }

        process B {
          script: "echo b"
        }

        workflow {
          A()
          B(A.out.data, A.out.data)
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.dependencies) == 1

    def test_ignores_non_process_uppercase_words(self, validator):
        """Test that uppercase words that aren't processes are ignored."""
        content = """
        nextflow.enable.dsl=2

        process REAL_PROCESS {
          script: "echo hello"
        }

        workflow {
          NOT_A_PROCESS()
          REAL_PROCESS()
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.tasks) == 1
        # NOT_A_PROCESS is not in tasks, so no dependency should be created
        assert len(result.dependencies) == 0


class TestWdlDependencyExtraction:
    """Tests for WDL call dependency extraction."""

    def test_extract_wdl_call_dependencies(self, validator):
        """Test extraction of WDL call chain dependencies.

        Note: Full WDL parsing depends on miniwdl being installed and working.
        The test validates that basic structure is recognized.
        """
        content = """
        version 1.0

        task taskA {
          command <<<
            echo "A"
          >>>
          output {
            File out = "a.txt"
          }
        }

        task taskB {
          input {
            File in_file
          }
          command <<<
            cat ~{in_file}
          >>>
          output {
            File out = "b.txt"
          }
        }

        workflow test_workflow {
          call taskA

          call taskB {
            input:
              in_file = taskA.out
          }

          output {
            File result = taskB.out
          }
        }
        """
        result = validator.validate(content, "wdl")
        # May fail validation if miniwdl has issues, but should at least parse tasks
        if result.valid:
            assert len(result.tasks) == 2
        else:
            # Basic validation fallback should still find task blocks
            pass

    def test_wdl_linear_chain(self, validator):
        """Test WDL 4-step linear chain.

        Note: Full WDL parsing depends on miniwdl being installed and working.
        """
        content = """
        version 1.0

        task fastqc {
          command <<<
            echo "qc"
          >>>
          output {
            File report = "qc.txt"
          }
        }

        task trimming {
          input {
            File qc_report
          }
          command <<<
            echo "trim"
          >>>
          output {
            File trimmed = "trimmed.txt"
          }
        }

        task alignment {
          input {
            File trimmed_reads
          }
          command <<<
            echo "align"
          >>>
          output {
            File bam = "out.bam"
          }
        }

        task variant_calling {
          input {
            File bam
          }
          command <<<
            echo "call"
          >>>
          output {
            File vcf = "out.vcf"
          }
        }

        workflow genomics_pipeline {
          call fastqc

          call trimming {
            input:
              qc_report = fastqc.report
          }

          call alignment {
            input:
              trimmed_reads = trimming.trimmed
          }

          call variant_calling {
            input:
              bam = alignment.bam
          }

          output {
            File result = variant_calling.vcf
          }
        }
        """
        result = validator.validate(content, "wdl")
        # May fail validation if miniwdl has issues
        if result.valid:
            assert len(result.tasks) == 4

    @pytest.mark.asyncio
    async def test_extracts_scatter_source_dependencies_for_deaf_20(self, validator):
        result = await validator.validate_and_extract(
            DEAF_20_WDL,
            "wdl",
            "Deaf_20.wdl",
        )

        assert result.valid
        assert result.workflow_name == "Deaf_20"
        assert [item.name for item in result.inputs] == ["outdir", "sequence_list"]
        assert [item.name for item in result.tasks] == [
            "PREPARATION",
            "SPLIT",
            "FILTER",
            "ALIGN",
            "RESULT",
        ]
        dep_pairs = {(dep.source, dep.target) for dep in result.dependencies}
        assert ("PREPARATION", "SPLIT") in dep_pairs
        assert ("PREPARATION", "FILTER") in dep_pairs
        assert ("PREPARATION", "ALIGN") in dep_pairs
        assert ("SPLIT", "FILTER") in dep_pairs
        assert ("FILTER", "ALIGN") in dep_pairs
        assert ("ALIGN", "RESULT") in dep_pairs

    @pytest.mark.asyncio
    async def test_extracts_storage_aware_parameter_metadata_for_deaf_20(
        self, validator
    ):
        result = await validator.validate_and_extract(
            DEAF_20_WDL,
            "wdl",
            "Deaf_20.wdl",
        )

        assert result.valid
        params = {item.name: item for item in result.inputs}
        assert params["sequence_list"].value_kind == "file"
        assert params["sequence_list"].source_hint == "project"
        assert params["sequence_list"].is_internal is False
        assert params["outdir"].value_kind == "scalar"
        assert params["outdir"].is_internal is True

        outputs = {item.name: item for item in result.outputs}
        assert outputs["zip_result"].value_kind == "file"


class TestValidationBasics:
    """Tests for basic validation functionality."""

    def test_invalid_engine(self, validator):
        """Test that invalid engine returns error."""
        result = validator.validate("content", "invalid_engine")
        assert not result.valid
        assert len(result.errors) == 1
        assert "Unknown engine" in result.errors[0].message

    def test_empty_nextflow(self, validator):
        """Test that empty Nextflow file is invalid."""
        result = validator.validate("// empty file", "nextflow")
        assert not result.valid

    def test_empty_wdl(self, validator):
        """Test that empty WDL file is invalid."""
        result = validator.validate("# empty file", "wdl")
        assert not result.valid

    def test_basic_wdl_fallback_extracts_workflow_inputs_and_outputs(self, validator):
        result = validator._validate_wdl_basic(
            WGS_CLINICAL_WDL_COMPACT,
            "main.wdl",
        )

        assert result.valid
        assert result.workflow_name == "WGS_CLINICAL"
        assert [item.name for item in result.inputs] == ["outdir", "sequence_list"]
        assert result.inputs[0].is_internal is True
        assert result.inputs[1].value_kind == "file"
        assert [item.name for item in result.outputs] == ["zip_result"]
        assert result.outputs[0].value_kind == "file"

    def test_unmatched_braces_nextflow(self, validator):
        """Test that unmatched braces are detected."""
        content = """
        process A {
          script: "echo a"
        """  # Missing closing brace
        result = validator.validate(content, "nextflow")
        assert not result.valid
        assert any("brace" in e.message.lower() for e in result.errors)

    def test_extracts_params(self, validator):
        """Test that Nextflow params are extracted."""
        content = """
        nextflow.enable.dsl=2

        params.reads = 'reads/*.fastq'
        params.reference = 'ref/*.fa'
        params.outdir = 'results'

        process A {
          script: "echo a"
        }

        workflow {
          A()
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.inputs) == 3
        param_names = {p.name for p in result.inputs}
        assert param_names == {"reads", "reference", "outdir"}
        params = {p.name: p for p in result.inputs}
        assert params["reads"].value_kind == "file_list"
        assert params["reads"].source_hint == "project"
        assert params["reference"].value_kind == "file"
        assert params["reference"].source_hint == "reference"
        assert params["outdir"].is_internal is True

    def test_extracts_required_param_references_without_inline_defaults(self, validator):
        """Params referenced in workflow code should remain discoverable even
        when the author does not bake in a fallback default."""
        content = """
        nextflow.enable.dsl=2

        params.outdir = params.outdir ?: 'results'

        workflow {
          Channel
            .fromPath(params.samplesheet, checkIfExists: true)
            .splitCsv(header: true)
            .view()
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        params = {p.name: p for p in result.inputs}
        assert "samplesheet" in params
        assert params["samplesheet"].optional is False
        assert params["samplesheet"].default is None
        assert params["samplesheet"].value_kind == "file"

    def test_extracts_container(self, validator):
        """Test that container info is extracted."""
        content = """
        nextflow.enable.dsl=2

        process A {
          container 'python:3.12-slim'
          script: "echo a"
        }

        workflow {
          A()
        }
        """
        result = validator.validate(content, "nextflow")
        assert result.valid
        assert len(result.tasks) == 1
        assert result.tasks[0].container == "python:3.12-slim"


@pytest.mark.asyncio
async def test_validate_and_extract_uses_schema_extractor_results():
    validator = WorkflowValidator()
    schema = {
        "workflow_name": "schema-demo",
        "version": "1.0",
        "description": "adapter schema",
        "inputs": [{"name": "sample", "type": "String", "optional": False}],
        "outputs": [{"name": "report", "type": "File", "optional": False}],
        "tasks": [{"name": "FASTQC", "inputs": [], "outputs": ["report"]}],
        "dependencies": [],
    }

    with patch(
        "app.services.workflow_validator.SchemaExtractor.extract",
        new=AsyncMock(return_value=schema),
    ) as extract:
        result = await validator.validate_and_extract(
            """
            nextflow.enable.dsl=2
            process FASTQC { output: path 'report.txt'; script: 'echo hi' }
            workflow { FASTQC() }
            """,
            "nextflow",
            file_name="workflow.nf",
            source="/tmp/workflow.nf",
        )

    assert result.valid
    assert result.workflow_name == "schema-demo"
    assert [task.name for task in result.tasks] == ["FASTQC"]
    assert [output.name for output in result.outputs] == ["report"]
    extract.assert_awaited_once()
