version 1.0

workflow parabricks_container_smoke {
  input {
    String sample_name = "parabricks_smoke"
    Int num_gpus = 0
    Int cpu = 2
    String memory = "8G"
    String disk = "local-disk 20 HDD"
    Boolean require_gpu = false
  }

  call smoke {
    input:
      sample_name = sample_name,
      num_gpus = num_gpus,
      cpu = cpu,
      memory = memory,
      disk = disk,
      require_gpu = require_gpu
  }

  output {
    File summary = smoke.summary
    File parabricks_version = smoke.parabricks_version
    File gpu_report = smoke.gpu_report
    File mock_vcf = smoke.mock_vcf
  }
}

task smoke {
  input {
    String sample_name
    Int num_gpus
    Int cpu
    String memory
    String disk
    Boolean require_gpu
  }

  command <<<
    set -euo pipefail

    {
      echo "sample_name=~{sample_name}"
      echo "container=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
      echo "num_gpus=~{num_gpus}"
      echo "require_gpu=~{require_gpu}"
      date -Iseconds
    } > smoke_summary.txt

    if command -v pbrun >/dev/null 2>&1; then
      (pbrun --version || pbrun version || pbrun --help || true) > parabricks_version.txt 2>&1
    else
      echo "pbrun executable not found" > parabricks_version.txt
      exit 127
    fi

    if command -v nvidia-smi >/dev/null 2>&1; then
      if ! nvidia-smi > nvidia-smi.txt 2>&1 && [ "~{require_gpu}" = "true" ]; then
        cat nvidia-smi.txt
        exit 1
      fi
    else
      echo "nvidia-smi executable not found" > nvidia-smi.txt
      if [ "~{require_gpu}" = "true" ]; then
        exit 1
      fi
    fi

    {
      echo "##fileformat=VCFv4.2"
      echo "##source=bioinfoflow-parabricks-container-smoke"
      echo "#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO"
      echo "chrSmoke	1	.	A	C	60	PASS	SAMPLE=~{sample_name}"
    } > "~{sample_name}.smoke.vcf"
  >>>

  output {
    File summary = "smoke_summary.txt"
    File parabricks_version = "parabricks_version.txt"
    File gpu_report = "nvidia-smi.txt"
    File mock_vcf = "~{sample_name}.smoke.vcf"
  }

  runtime {
    docker: "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    cpu: cpu
    memory: memory
    disks: disk
  }
}
