version 1.0

workflow align_pipeline {
    input {
        String outdir
        String sample_id
        File trimmed_reads
    }

    call INDEX_REF {
        input:
            outdir = outdir
    }

    call BWA_MEM {
        input:
            outdir = outdir,
            sample_id = sample_id,
            trimmed_reads = trimmed_reads,
            reference_index = INDEX_REF.reference_index
    }

    call SORT_BAM {
        input:
            outdir = outdir,
            sample_id = sample_id,
            raw_bam = BWA_MEM.raw_bam
    }

    output {
        File sorted_bam = SORT_BAM.sorted_bam
    }
}

task INDEX_REF {
    input {
        String outdir
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/align/01.index
        # Mock reference index.
        cat > ~{outdir}/align/01.index/ref.fa.index <<EOF
mock_reference_index
built_at=$(date -Iseconds)
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
        File reference_index = "${outdir}/align/01.index/ref.fa.index"
    }
}

task BWA_MEM {
    input {
        String outdir
        String sample_id
        File trimmed_reads
        File reference_index
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/align/02.bwa_mem
        cat > ~{outdir}/align/02.bwa_mem/~{sample_id}.raw.bam <<EOF
@HD	VN:1.6	SO:unsorted
@MOCK	sample=~{sample_id}
@MOCK	reads=~{trimmed_reads}
@MOCK	index=~{reference_index}
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
        File raw_bam = "${outdir}/align/02.bwa_mem/${sample_id}.raw.bam"
    }
}

task SORT_BAM {
    input {
        String outdir
        String sample_id
        File raw_bam
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/align/03.sort
        # Mock sort: replace SO:unsorted with SO:coordinate in the header.
        sed 's/SO:unsorted/SO:coordinate/' ~{raw_bam} > ~{outdir}/align/03.sort/~{sample_id}.sorted.bam
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
        File sorted_bam = "${outdir}/align/03.sort/${sample_id}.sorted.bam"
    }
}
