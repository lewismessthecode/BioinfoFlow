version 1.0

workflow viral_qc {
  input {
    Array[File] reads
    File reference
    String outdir = "results"
  }

  call reads_stats {
    input:
      reads = reads
  }

  call reference_stats {
    input:
      reference = reference
  }

  call summary_report {
    input:
      reads_report = reads_stats.reads_report,
      reference_report = reference_stats.reference_report,
      outdir = outdir
  }

  output {
    File report = summary_report.report
  }
}

task reads_stats {
  input {
    Array[File] reads
  }

  command <<<
    echo "reads" > reads.txt
  >>>

  output {
    File reads_report = "reads.txt"
  }

  runtime {
    image: "python:3.12-slim"
  }
}

task reference_stats {
  input {
    File reference
  }

  command <<<
    echo "reference" > reference.txt
  >>>

  output {
    File reference_report = "reference.txt"
  }

  runtime {
    image: "python:3.12-slim"
  }
}

task summary_report {
  input {
    File reads_report
    File reference_report
    String outdir
  }

  command <<<
    echo "~{reads_report}" > summary.txt
    echo "~{reference_report}" >> summary.txt
    echo "~{outdir}" >> summary.txt
  >>>

  output {
    File report = "summary.txt"
  }

  runtime {
    image: "python:3.12-slim"
  }
}
