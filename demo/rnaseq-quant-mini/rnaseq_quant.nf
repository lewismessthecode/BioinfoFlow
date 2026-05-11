nextflow.enable.dsl = 2

params.outdir = params.outdir ?: "results"
params.genome = params.genome ?: "GRCh38"

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

workflow {
    samples_ch = Channel
        .fromPath(params.samplesheet, checkIfExists: true)
        .splitCsv(header: true)
        .map { row ->
            tuple(
                row.sample,
                file(resolveManifestPath(row.fastq_1)),
                file(resolveManifestPath(row.fastq_2)),
                row.strandedness ?: "auto"
            )
        }

    fastqc_out = FASTQC(samples_ch)
    trim_out   = TRIM(fastqc_out.reads)
    align_out  = ALIGN(trim_out.trimmed, params.genome)
    quant_out  = QUANT(align_out.bam)
    MULTIQC(fastqc_out.report.collect(), quant_out.quant.collect())
}

process FASTQC {
    tag { sample }
    publishDir "${params.outdir}/fastqc", mode: "copy", pattern: "*.html"
    container "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0"

    input:
        tuple val(sample), path(fastq_1), path(fastq_2), val(strandedness)

    output:
        tuple val(sample), path(fastq_1), path(fastq_2), val(strandedness), emit: reads
        path("${sample}.fastqc.html"), emit: report

    script:
    """
    # Minimal mock HTML — we want to test the remote image pull path, not fastqc itself.
    cat > ${sample}.fastqc.html <<EOF
    <html><body>
    <h1>${sample}</h1>
    <p>fastq_1=${fastq_1}</p>
    <p>fastq_2=${fastq_2}</p>
    <p>strandedness=${strandedness}</p>
    </body></html>
    EOF
    """
}

process TRIM {
    tag { sample }
    publishDir "${params.outdir}/trim", mode: "copy", pattern: "*.trimmed.fq.gz"
    container "ubuntu:22.04"

    input:
        tuple val(sample), path(fastq_1), path(fastq_2), val(strandedness)

    output:
        tuple val(sample), path("${sample}.trimmed.fq.gz"), val(strandedness), emit: trimmed

    script:
    """
    echo -e "@${sample}_trimmed\\nACGT\\n+\\nIIII" | gzip > ${sample}.trimmed.fq.gz
    """
}

process ALIGN {
    tag { "${sample}:${genome}" }
    publishDir "${params.outdir}/align", mode: "copy", pattern: "*.bam"
    container "ubuntu:22.04"

    input:
        tuple val(sample), path(trimmed), val(strandedness)
        val genome

    output:
        tuple val(sample), path("${sample}.bam"), val(strandedness), emit: bam

    script:
    """
    cat > ${sample}.bam <<EOF
    @HD	VN:1.6	SO:coordinate
    @MOCK	sample=${sample}
    @MOCK	genome=${genome}
    @MOCK	strandedness=${strandedness}
    @MOCK	trimmed=${trimmed}
    EOF
    """
}

process QUANT {
    tag { sample }
    publishDir "${params.outdir}/quant", mode: "copy"
    container "ubuntu:22.04"

    input:
        tuple val(sample), path(bam), val(strandedness)

    output:
        path("${sample}"), emit: quant

    script:
    """
    mkdir -p ${sample}
    cat > ${sample}/quant.sf <<EOF
    Name	Length	EffectiveLength	TPM	NumReads
    MOCK_GENE_1	1000	950	1234.5	100
    MOCK_GENE_2	500	450	678.9	50
    EOF
    """
}

process MULTIQC {
    publishDir "${params.outdir}/multiqc", mode: "copy"
    container "ubuntu:22.04"

    input:
        path("fastqc/*")
        path("quant/*")

    output:
        path("multiqc_report.html")

    script:
    """
    fastqc_count=\$(ls fastqc/ | wc -l)
    quant_count=\$(ls quant/ | wc -l)
    cat > multiqc_report.html <<EOF
    <html><body>
    <h1>MultiQC (mock)</h1>
    <p>fastqc inputs: \$fastqc_count</p>
    <p>quant inputs: \$quant_count</p>
    <p>generated_at=\$(date -Iseconds)</p>
    </body></html>
    EOF
    """
}
