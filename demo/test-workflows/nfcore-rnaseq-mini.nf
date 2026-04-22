nextflow.enable.dsl = 2

params.input = params.input ?: "samplesheet.csv"
params.outdir = params.outdir ?: "results"
params.genome = params.genome ?: "GRCh38"
params.aligner = params.aligner ?: "star_salmon"

workflow {
  samples_ch = Channel
    .fromPath(params.input, checkIfExists: false)
    .splitCsv(header: true)
    .map { row -> tuple(row.sample, row.fastq_1, row.fastq_2, row.strandedness ?: "auto") }

  FASTQ_QC(samples_ch)
}

process FASTQ_QC {
  tag { sample_id }

  input:
    tuple val(sample_id), val(fastq_1), val(fastq_2), val(strandedness)

  output:
    path("${sample_id}.qc.txt")

  script:
  """
  cat <<EOF > ${sample_id}.qc.txt
  sample=${sample_id}
  fastq_1=${fastq_1}
  fastq_2=${fastq_2}
  strandedness=${strandedness}
  genome=${params.genome}
  aligner=${params.aligner}
  outdir=${params.outdir}
  EOF
  """
}
