nextflow.enable.dsl = 2

if (!params.containsKey("samplesheet")) params.samplesheet = "samplesheet.csv"
if (!params.containsKey("reference")) params.reference = null
if (!params.containsKey("reference_indexes")) params.reference_indexes = []
if (!params.containsKey("known_sites")) params.known_sites = null
if (!params.containsKey("known_sites_indexes")) params.known_sites_indexes = []
if (!params.containsKey("outdir")) params.outdir = "results"
if (!params.containsKey("num_gpus")) params.num_gpus = 1
if (!params.containsKey("cpus")) params.cpus = 16
if (!params.containsKey("memory")) params.memory = "96 GB"
if (!params.containsKey("fq2bam_extra_args")) params.fq2bam_extra_args = ""
if (!params.containsKey("haplotypecaller_extra_args")) params.haplotypecaller_extra_args = ""

def resolveManifestPath = { raw ->
    def candidate = raw?.toString()?.trim()
    if (!candidate) {
        return candidate
    }
    if (candidate.startsWith("/")) {
        return candidate
    }
    return file(params.samplesheet).parent.resolve(candidate).toString()
}

def asFileList = { raw ->
    if (!raw) {
        return []
    }
    if (raw instanceof List) {
        return raw
            .findAll { it != null && it.toString().trim() }
            .collect { file(it.toString()) }
    }
    def candidate = raw.toString().trim()
    return candidate ? [file(candidate)] : []
}

workflow {
    if (!params.reference) {
        error "Missing required parameter: --reference"
    }
    if (!params.known_sites) {
        error "Missing required parameter: --known_sites"
    }

    samples_ch = Channel
        .fromPath(params.samplesheet, checkIfExists: true)
        .splitCsv(header: true)
        .map { row ->
            def sample = row.sample?.toString()?.trim()
            if (!sample) {
                error "samplesheet row is missing sample"
            }
            tuple(
                sample,
                file(resolveManifestPath(row.fastq_1)),
                file(resolveManifestPath(row.fastq_2)),
                row.read_group?.toString()?.trim() ?: "@RG\\tID:${sample}\\tLB:${sample}\\tPL:ILLUMINA\\tSM:${sample}\\tPU:${sample}"
            )
        }

    reference_ch = Channel.value(file(params.reference))
    reference_indexes_ch = Channel.value(asFileList(params.reference_indexes))
    known_sites_ch = Channel.value(file(params.known_sites))
    known_sites_indexes_ch = Channel.value(asFileList(params.known_sites_indexes))

    fq2bam_out = FQ2BAM(samples_ch, reference_ch, reference_indexes_ch, known_sites_ch, known_sites_indexes_ch)
    HAPLOTYPECALLER(fq2bam_out.bam, reference_ch, reference_indexes_ch)
}

process FQ2BAM {
    tag { sample }
    container "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    cpus params.cpus
    memory params.memory
    publishDir "${params.outdir}/fq2bam", mode: "copy"

    input:
        tuple val(sample), path(fastq_1), path(fastq_2), val(read_group)
        path reference
        path reference_indexes
        path known_sites
        path known_sites_indexes

    output:
        tuple val(sample), path("${sample}.pb.bam"), path("${sample}.pb.bam.bai"), path("${sample}.pb.recal.txt"), emit: bam
        path("${sample}.pb.duplicate-metrics.txt"), emit: duplicate_metrics

    script:
    """
    set -euo pipefail

    pbrun fq2bam \\
      --ref "${reference}" \\
      --in-fq "${fastq_1}" "${fastq_2}" "${read_group}" \\
      --knownSites "${known_sites}" \\
      --out-bam "${sample}.pb.bam" \\
      --out-recal-file "${sample}.pb.recal.txt" \\
      --out-duplicate-metrics "${sample}.pb.duplicate-metrics.txt" \\
      --num-gpus ${params.num_gpus} \\
      ${params.fq2bam_extra_args}

    if [ -f "${sample}.pb.bam.BAI" ] && [ ! -f "${sample}.pb.bam.bai" ]; then
      cp "${sample}.pb.bam.BAI" "${sample}.pb.bam.bai"
    fi

    test -s "${sample}.pb.bam"
    test -s "${sample}.pb.bam.bai"
    """

    stub:
    """
    touch "${sample}.pb.bam"
    touch "${sample}.pb.bam.bai"
    touch "${sample}.pb.recal.txt"
    touch "${sample}.pb.duplicate-metrics.txt"
    """
}

process HAPLOTYPECALLER {
    tag { sample }
    container "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    cpus params.cpus
    memory params.memory
    publishDir "${params.outdir}/haplotypecaller", mode: "copy"

    input:
        tuple val(sample), path(bam), path(bam_index), path(recal_table)
        path reference
        path reference_indexes

    output:
        path("${sample}.pb.vcf"), emit: vcf

    script:
    """
    set -euo pipefail

    pbrun haplotypecaller \\
      --ref "${reference}" \\
      --in-bam "${bam}" \\
      --in-recal-file "${recal_table}" \\
      --out-variants "${sample}.pb.vcf" \\
      --num-gpus ${params.num_gpus} \\
      ${params.haplotypecaller_extra_args}

    test -s "${sample}.pb.vcf"
    """

    stub:
    """
    touch "${sample}.pb.vcf"
    """
}
