version 1.0

import "subworkflows/qc_sub.wdl" as QC
import "subworkflows/align_sub.wdl" as ALIGN

workflow subworkflow_import_demo {
  input {
    File reads_fastq
    File reference_fasta
    String sample_id = "demo"
  }

  call QC.QC_FLOW {
    input:
      reads_fastq = reads_fastq,
      sample_id = sample_id
  }

  call ALIGN.ALIGN_FLOW {
    input:
      reads_fastq = QC_FLOW.trimmed_fastq,
      reference_fasta = reference_fasta,
      sample_id = sample_id
  }

  output {
    File qc_report = QC_FLOW.qc_report
    File bam = ALIGN_FLOW.sorted_bam
    File report = ALIGN_FLOW.report
  }
}
