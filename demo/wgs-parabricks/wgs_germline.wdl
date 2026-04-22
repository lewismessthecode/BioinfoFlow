version 1.0

workflow wgs_germline {
  input {
    Array[File] fastq_r1
    Array[File] fastq_r2
    File reference
    File known_sites
    String outdir = "results"
  }

  call fq2bam {
    input:
      fastq_r1 = fastq_r1,
      fastq_r2 = fastq_r2,
      reference = reference
  }

  call haplotypecaller {
    input:
      bam = fq2bam.bam,
      reference = reference,
      known_sites = known_sites,
      outdir = outdir
  }

  output {
    File vcf = haplotypecaller.vcf
  }
}

task fq2bam {
  input {
    Array[File] fastq_r1
    Array[File] fastq_r2
    File reference
  }

  command <<<
    echo "bam" > sample.bam
  >>>

  output {
    File bam = "sample.bam"
  }

  runtime {
    image: "nvcr.io/nvidia/clara/clara-parabricks:4.1.0-1"
  }
}

task haplotypecaller {
  input {
    File bam
    File reference
    File known_sites
    String outdir
  }

  command <<<
    echo "vcf" > output.vcf.gz
  >>>

  output {
    File vcf = "output.vcf.gz"
  }

  runtime {
    image: "nvcr.io/nvidia/clara/clara-parabricks:4.1.0-1"
  }
}
