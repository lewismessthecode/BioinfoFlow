nextflow.enable.dsl = 2

params.input = params.input ?: "samplesheet.csv"
params.outdir = params.outdir ?: "results"
params.genome = params.genome ?: "GRCh38"
params.tools = params.tools ?: "mutect2,strelka"

workflow {
  pairs_ch = Channel
    .fromPath(params.input, checkIfExists: false)
    .splitCsv(header: true)
    .map { row ->
      tuple(
        row.patient,
        row.sample,
        row.lane ?: "L001",
        row.fastq_1,
        row.fastq_2,
        row.status ?: "0"
      )
    }

  PAIR_SUMMARY(pairs_ch)
}

process PAIR_SUMMARY {
  tag { "${patient}:${sample}" }

  input:
    tuple val(patient), val(sample), val(lane), val(fastq_1), val(fastq_2), val(status)

  output:
    path("${patient}_${sample}.pair.txt")

  script:
  """
  cat <<EOF > ${patient}_${sample}.pair.txt
  patient=${patient}
  sample=${sample}
  lane=${lane}
  fastq_1=${fastq_1}
  fastq_2=${fastq_2}
  status=${status}
  genome=${params.genome}
  tools=${params.tools}
  outdir=${params.outdir}
  EOF
  """
}
