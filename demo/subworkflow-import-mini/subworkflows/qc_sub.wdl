version 1.0

workflow qc_pipeline {
    input {
        String outdir
        String sample_id
    }

    call FASTQC {
        input:
            outdir = outdir,
            sample_id = sample_id
    }

    call TRIM {
        input:
            outdir = outdir,
            sample_id = sample_id,
            fastqc_report = FASTQC.report
    }

    call POST_QC {
        input:
            outdir = outdir,
            sample_id = sample_id,
            trimmed_reads = TRIM.trimmed
    }

    output {
        File qc_summary = POST_QC.summary
        File trimmed_reads = TRIM.trimmed
    }
}

task FASTQC {
    input {
        String outdir
        String sample_id
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/qc/01.fastqc
        cat > ~{outdir}/qc/01.fastqc/~{sample_id}.report.txt <<EOF
sample=~{sample_id}
qc_at=$(date -Iseconds)
quality=mock-pass
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
        File report = "${outdir}/qc/01.fastqc/${sample_id}.report.txt"
    }
}

task TRIM {
    input {
        String outdir
        String sample_id
        File fastqc_report
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/qc/02.trim
        # Mock trimmed output; prove File input actually arrived.
        cat > ~{outdir}/qc/02.trim/~{sample_id}.trimmed.fq <<EOF
@~{sample_id}-read1
ACGTACGTACGT
+
IIIIIIIIIIII
# source_report=~{fastqc_report}
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
        File trimmed = "${outdir}/qc/02.trim/${sample_id}.trimmed.fq"
    }
}

task POST_QC {
    input {
        String outdir
        String sample_id
        File trimmed_reads
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/qc/03.post_qc
        read_count=$(grep -c '^@' ~{trimmed_reads} || echo 0)
        cat > ~{outdir}/qc/03.post_qc/~{sample_id}.summary.txt <<EOF
sample=~{sample_id}
reads_retained=$read_count
trimmed_file=~{trimmed_reads}
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
        File summary = "${outdir}/qc/03.post_qc/${sample_id}.summary.txt"
    }
}
