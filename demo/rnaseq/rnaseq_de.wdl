version 1.0

workflow rnaseq_de {
  input {
    Array[File] fastq_r1
    Array[File] fastq_r2
    File reference
    String outdir = "results"
  }

  call fastqc {
    input:
      fastq_r1 = fastq_r1,
      fastq_r2 = fastq_r2
  }

  call trimming {
    input:
      fastq_r1 = fastq_r1,
      fastq_r2 = fastq_r2
  }

  call star_alignment {
    input:
      trimmed_r1 = trimming.trimmed_r1,
      trimmed_r2 = trimming.trimmed_r2,
      reference = reference
  }

  call quantification {
    input:
      aligned_bam = star_alignment.aligned_bam
  }

  call differential_expression {
    input:
      counts = quantification.counts,
      outdir = outdir
  }

  output {
    File report = differential_expression.report
  }
}

task fastqc {
  input {
    Array[File] fastq_r1
    Array[File] fastq_r2
  }

  command <<<
    echo "fastqc" > fastqc.txt
  >>>

  output {
    File qc_report = "fastqc.txt"
  }

  runtime {
    image: "quay.io/biocontainers/fastqc:0.12.1"
  }
}

task trimming {
  input {
    Array[File] fastq_r1
    Array[File] fastq_r2
  }

  command <<<
    echo "trim" > trimmed_R1.fastq.gz
    echo "trim" > trimmed_R2.fastq.gz
  >>>

  output {
    File trimmed_r1 = "trimmed_R1.fastq.gz"
    File trimmed_r2 = "trimmed_R2.fastq.gz"
  }

  runtime {
    image: "quay.io/biocontainers/trim-galore:0.6.10"
  }
}

task star_alignment {
  input {
    File trimmed_r1
    File trimmed_r2
    File reference
  }

  command <<<
    echo "bam" > aligned.bam
  >>>

  output {
    File aligned_bam = "aligned.bam"
  }

  runtime {
    image: "quay.io/biocontainers/star:2.7.11b"
  }
}

task quantification {
  input {
    File aligned_bam
  }

  command <<<
    echo "counts" > counts.txt
  >>>

  output {
    File counts = "counts.txt"
  }

  runtime {
    image: "quay.io/biocontainers/subread:2.0.6"
  }
}

task differential_expression {
  input {
    File counts
    String outdir
  }

  command <<<
    echo "~{counts}" > de_report.txt
    echo "~{outdir}" >> de_report.txt
  >>>

  output {
    File report = "de_report.txt"
  }

  runtime {
    image: "python:3.12-slim"
  }
}
