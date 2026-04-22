version 1.0

import "subworkflows/qc_sub.wdl" as qc
import "subworkflows/align_sub.wdl" as align

workflow subworkflow_import_mini {
    input {
        String outdir
        String sample_id
    }

    meta {
        pipeline_version: "1.0.0"
        description: "Main workflow importing two subworkflows to test import resolution and nested DAG rendering."
    }

    call qc.qc_pipeline as qc_run {
        input:
            outdir = outdir,
            sample_id = sample_id
    }

    call align.align_pipeline as align_run {
        input:
            outdir = outdir,
            sample_id = sample_id,
            trimmed_reads = qc_run.trimmed_reads
    }

    call REPORT {
        input:
            outdir = outdir,
            sample_id = sample_id,
            qc_summary = qc_run.qc_summary,
            sorted_bam = align_run.sorted_bam
    }

    output {
        File final_report = REPORT.final_report
    }
}

task REPORT {
    input {
        String outdir
        String sample_id
        File qc_summary
        File sorted_bam
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/99.report
        cat > ~{outdir}/99.report/~{sample_id}.final_report.txt <<EOF
sample=~{sample_id}
qc_summary=~{qc_summary}
sorted_bam=~{sorted_bam}
generated_at=$(date -Iseconds)

--- QC summary ---
$(cat ~{qc_summary})

--- Sorted BAM header ---
$(cat ~{sorted_bam})
EOF
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "5m"
    }

    output {
        File final_report = "${outdir}/99.report/${sample_id}.final_report.txt"
    }
}
