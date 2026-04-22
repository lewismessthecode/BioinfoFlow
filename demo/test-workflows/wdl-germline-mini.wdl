version 1.0

workflow germline_qc_mini {
  input {
    String sample_id
    File fastq_r1
    File fastq_r2
    String outdir = "results"
  }

  call fastq_qc_summary {
    input:
      sample_id = sample_id,
      fastq_r1 = fastq_r1,
      fastq_r2 = fastq_r2
  }

  output {
    File qc_report = fastq_qc_summary.report
  }
}

task fastq_qc_summary {
  input {
    String sample_id
    File fastq_r1
    File fastq_r2
  }

  command <<<
    cat <<EOF > ~{sample_id}.qc.txt
    sample_id=~{sample_id}
    fastq_r1=~{fastq_r1}
    fastq_r2=~{fastq_r2}
    EOF
  >>>

  output {
    File report = "~{sample_id}.qc.txt"
  }

  runtime {
    cpu: 1
    memory: "1G"
  }
}
