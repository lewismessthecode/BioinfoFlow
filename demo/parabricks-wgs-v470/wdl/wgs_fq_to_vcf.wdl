version 1.0

workflow parabricks_wgs_fq_to_vcf {
  input {
    String sample_name
    File fastq_r1
    File fastq_r2
    String read_group
    File reference
    Array[File] reference_indexes = []
    File known_sites
    Array[File] known_sites_indexes = []
    String out_prefix = sample_name
    Int num_gpus = 1
    Int cpu = 16
    String memory = "96G"
    String disk = "local-disk 1000 HDD"
    String fq2bam_extra_args = ""
    String haplotypecaller_extra_args = ""
  }

  call fq2bam {
    input:
      fastq_r1 = fastq_r1,
      fastq_r2 = fastq_r2,
      read_group = read_group,
      reference = reference,
      reference_indexes = reference_indexes,
      known_sites = known_sites,
      known_sites_indexes = known_sites_indexes,
      out_prefix = out_prefix,
      num_gpus = num_gpus,
      cpu = cpu,
      memory = memory,
      disk = disk,
      extra_args = fq2bam_extra_args
  }

  call haplotypecaller {
    input:
      bam = fq2bam.bam,
      bam_index = fq2bam.bam_index,
      recal_table = fq2bam.recal_table,
      reference = reference,
      reference_indexes = reference_indexes,
      out_prefix = out_prefix,
      num_gpus = num_gpus,
      cpu = cpu,
      memory = memory,
      disk = disk,
      extra_args = haplotypecaller_extra_args
  }

  output {
    File bam = fq2bam.bam
    File bam_index = fq2bam.bam_index
    File recal_table = fq2bam.recal_table
    File duplicate_metrics = fq2bam.duplicate_metrics
    File vcf = haplotypecaller.vcf
  }
}

task fq2bam {
  input {
    File fastq_r1
    File fastq_r2
    String read_group
    File reference
    Array[File] reference_indexes
    File known_sites
    Array[File] known_sites_indexes
    String out_prefix
    Int num_gpus
    Int cpu
    String memory
    String disk
    String extra_args
  }

  command <<<
    set -euo pipefail

    for f in ~{sep=' ' reference_indexes}; do
      test -s "$f"
    done
    for f in ~{sep=' ' known_sites_indexes}; do
      test -s "$f"
    done

    pbrun fq2bam \
      --ref "~{reference}" \
      --in-fq "~{fastq_r1}" "~{fastq_r2}" "~{read_group}" \
      --knownSites "~{known_sites}" \
      --out-bam "~{out_prefix}.pb.bam" \
      --out-recal-file "~{out_prefix}.pb.recal.txt" \
      --out-duplicate-metrics "~{out_prefix}.pb.duplicate-metrics.txt" \
      --num-gpus ~{num_gpus} \
      ~{extra_args}

    if [ -f "~{out_prefix}.pb.bam.BAI" ] && [ ! -f "~{out_prefix}.pb.bam.bai" ]; then
      cp "~{out_prefix}.pb.bam.BAI" "~{out_prefix}.pb.bam.bai"
    fi

    test -s "~{out_prefix}.pb.bam"
    test -s "~{out_prefix}.pb.bam.bai"
  >>>

  output {
    File bam = "~{out_prefix}.pb.bam"
    File bam_index = "~{out_prefix}.pb.bam.bai"
    File recal_table = "~{out_prefix}.pb.recal.txt"
    File duplicate_metrics = "~{out_prefix}.pb.duplicate-metrics.txt"
  }

  runtime {
    docker: "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    cpu: cpu
    memory: memory
    disks: disk
    gpu: num_gpus > 0
  }
}

task haplotypecaller {
  input {
    File bam
    File bam_index
    File recal_table
    File reference
    Array[File] reference_indexes
    String out_prefix
    Int num_gpus
    Int cpu
    String memory
    String disk
    String extra_args
  }

  command <<<
    set -euo pipefail

    test -s "~{bam_index}"
    for f in ~{sep=' ' reference_indexes}; do
      test -s "$f"
    done

    pbrun haplotypecaller \
      --ref "~{reference}" \
      --in-bam "~{bam}" \
      --in-recal-file "~{recal_table}" \
      --out-variants "~{out_prefix}.pb.vcf" \
      --num-gpus ~{num_gpus} \
      ~{extra_args}

    test -s "~{out_prefix}.pb.vcf"
  >>>

  output {
    File vcf = "~{out_prefix}.pb.vcf"
  }

  runtime {
    docker: "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    cpu: cpu
    memory: memory
    disks: disk
    gpu: num_gpus > 0
  }
}
