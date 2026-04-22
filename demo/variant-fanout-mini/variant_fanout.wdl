version 1.0

workflow variant_fanout_mini {
    input {
        String outdir
        File samples_tsv
    }

    meta {
        pipeline_version: "1.0.0"
        description: "Scatter/gather with real File flow: ALIGN -> CALL -> MERGE -> FILTER -> ANNOTATE -> REPORT."
    }

    call PREP {
        input:
            outdir = outdir,
            samples_tsv = samples_tsv
    }

    # Each TSV line becomes Array[String]; column 0 = sample_id, column 1 = mock reads path.
    scatter (row in read_tsv(PREP.sample_table)) {
        call ALIGN {
            input:
                outdir = outdir,
                sample_id = row[0],
                mock_reads = row[1]
        }

        call CALL {
            input:
                outdir = outdir,
                sample_id = row[0],
                bam = ALIGN.bam
        }
    }

    call MERGE {
        input:
            outdir = outdir,
            vcfs = CALL.vcf
    }

    call FILTER {
        input:
            outdir = outdir,
            merged_vcf = MERGE.merged_vcf
    }

    call ANNOTATE {
        input:
            outdir = outdir,
            filtered_vcf = FILTER.filtered_vcf
    }

    call REPORT {
        input:
            outdir = outdir,
            annotated_tsv = ANNOTATE.annotated_tsv
    }

    output {
        File report_zip = REPORT.report_zip
    }
}

task PREP {
    input {
        String outdir
        File samples_tsv
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/01.prep
        # Strip header line; scatter consumes sample rows only.
        tail -n +2 ~{samples_tsv} > ~{outdir}/01.prep/sample_table.tsv
        wc -l < ~{outdir}/01.prep/sample_table.tsv > ~{outdir}/01.prep/sample_count.txt
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
        File sample_table = "${outdir}/01.prep/sample_table.tsv"
    }
}

task ALIGN {
    input {
        String outdir
        String sample_id
        String mock_reads
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/02.align
        # Mock BAM: header line + metadata; downstream CALL will parse this as input.
        cat > ~{outdir}/02.align/~{sample_id}.bam <<EOF
@HD	VN:1.6	SO:coordinate
@MOCK	sample=~{sample_id}
@MOCK	reads=~{mock_reads}
@MOCK	aligned_at=$(date -Iseconds)
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
        File bam = "${outdir}/02.align/${sample_id}.bam"
    }
}

task CALL {
    input {
        String outdir
        String sample_id
        File bam
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/03.call
        # Mock VCF built from the BAM metadata; proves the File actually reached this task.
        cat > ~{outdir}/03.call/~{sample_id}.vcf <<EOF
##fileformat=VCFv4.2
##source=mock-caller
##input_bam=~{bam}
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
chr1	100	.	A	T	30	PASS	SAMPLE=~{sample_id}
chr2	200	.	G	C	40	PASS	SAMPLE=~{sample_id}
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
        File vcf = "${outdir}/03.call/${sample_id}.vcf"
    }
}

task MERGE {
    input {
        String outdir
        Array[File] vcfs
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/04.merge
        out=~{outdir}/04.merge/merged.vcf
        first=true
        for f in ~{sep=" " vcfs}; do
            if $first; then
                cat "$f" > "$out"
                first=false
            else
                grep -v '^#' "$f" >> "$out" || true
            fi
        done
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
        File merged_vcf = "${outdir}/04.merge/merged.vcf"
    }
}

task FILTER {
    input {
        String outdir
        File merged_vcf
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/05.filter
        # Keep PASS records + header; drop anything else.
        awk '/^#/ || $7 == "PASS"' ~{merged_vcf} > ~{outdir}/05.filter/filtered.vcf
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
        File filtered_vcf = "${outdir}/05.filter/filtered.vcf"
    }
}

task ANNOTATE {
    input {
        String outdir
        File filtered_vcf
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/06.annotate
        out=~{outdir}/06.annotate/annotated.tsv
        echo -e "chrom\tpos\tref\talt\tsample\tannotation" > "$out"
        grep -v '^#' ~{filtered_vcf} | awk 'BEGIN{OFS="\t"} {
            split($8, kv, ";"); sample=""; for (i in kv) { split(kv[i], parts, "="); if (parts[1] == "SAMPLE") sample=parts[2] }
            print $1, $2, $4, $5, sample, "mock-annotation"
        }' >> "$out"
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
        File annotated_tsv = "${outdir}/06.annotate/annotated.tsv"
    }
}

task REPORT {
    input {
        String outdir
        File annotated_tsv
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/07.report
        # zip is not in the base ubuntu image by default; use tar.gz and name the output report.zip
        # so the platform sees a single artifact at the declared path.
        tar -czf ~{outdir}/07.report/report.zip -C $(dirname ~{annotated_tsv}) $(basename ~{annotated_tsv})
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
        File report_zip = "${outdir}/07.report/report.zip"
    }
}
