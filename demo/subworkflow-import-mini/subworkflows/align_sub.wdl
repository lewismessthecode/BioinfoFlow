version 1.0

workflow ALIGN_FLOW {
  input {
    File reads_fastq
    File reference_fasta
    String sample_id
  }

  call INDEX_REF {
    input:
      reference_fasta = reference_fasta
  }

  call BWA_MEM {
    input:
      reads_fastq = reads_fastq,
      reference_fasta = reference_fasta,
      index_marker = INDEX_REF.index_marker,
      sample_id = sample_id
  }

  call SORT_BAM {
    input:
      sam_file = BWA_MEM.sam_file,
      sample_id = sample_id
  }

  call REPORT {
    input:
      sorted_bam = SORT_BAM.sorted_bam,
      sample_id = sample_id
  }

  output {
    File sorted_bam = SORT_BAM.sorted_bam
    File report = REPORT.report
  }
}

task INDEX_REF {
  input {
    File reference_fasta
  }

  command <<<
    set -euo pipefail
    printf "indexed\t~{reference_fasta}\n" > reference.index.txt
  >>>

  output {
    File index_marker = "reference.index.txt"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}

task BWA_MEM {
  input {
    File reads_fastq
    File reference_fasta
    File index_marker
    String sample_id
  }

  command <<<
    set -euo pipefail
    printf "sam\t~{sample_id}\t~{reads_fastq}\t~{reference_fasta}\t~{index_marker}\n" > aligned.sam
  >>>

  output {
    File sam_file = "aligned.sam"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}

task SORT_BAM {
  input {
    File sam_file
    String sample_id
  }

  command <<<
    set -euo pipefail
    printf "bam\t~{sample_id}\t~{sam_file}\n" > sorted.bam
  >>>

  output {
    File sorted_bam = "sorted.bam"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}

task REPORT {
  input {
    File sorted_bam
    String sample_id
  }

  command <<<
    set -euo pipefail
    printf "report\t~{sample_id}\t~{sorted_bam}\n" > alignment_report.txt
  >>>

  output {
    File report = "alignment_report.txt"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}
