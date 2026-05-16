version 1.0

workflow QC_FLOW {
  input {
    File reads_fastq
    String sample_id
  }

  call FASTQC {
    input:
      reads_fastq = reads_fastq,
      sample_id = sample_id
  }

  call TRIM {
    input:
      reads_fastq = reads_fastq,
      sample_id = sample_id
  }

  call POST_QC {
    input:
      trimmed_fastq = TRIM.trimmed_fastq,
      sample_id = sample_id
  }

  output {
    File qc_report = POST_QC.qc_report
    File trimmed_fastq = TRIM.trimmed_fastq
  }
}

task FASTQC {
  input {
    File reads_fastq
    String sample_id
  }

  command <<<
    set -euo pipefail
    printf "fastqc\t~{sample_id}\t~{reads_fastq}\n" > fastqc.txt
  >>>

  output {
    File report = "fastqc.txt"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}

task TRIM {
  input {
    File reads_fastq
    String sample_id
  }

  command <<<
    set -euo pipefail
    cp "~{reads_fastq}" "~{sample_id}.trimmed.fastq"
  >>>

  output {
    File trimmed_fastq = "~{sample_id}.trimmed.fastq"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}

task POST_QC {
  input {
    File trimmed_fastq
    String sample_id
  }

  command <<<
    set -euo pipefail
    printf "post-qc\t~{sample_id}\t~{trimmed_fastq}\n" > post_qc.txt
  >>>

  output {
    File qc_report = "post_qc.txt"
  }

  runtime {
    docker: "ubuntu:22.04"
  }
}
