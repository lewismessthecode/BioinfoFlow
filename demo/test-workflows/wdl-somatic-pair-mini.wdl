version 1.0

workflow somatic_pair_mini {
  input {
    String patient_id
    File tumor_bam
    File normal_bam
    String outdir = "results"
  }

  call pair_manifest {
    input:
      patient_id = patient_id,
      tumor_bam = tumor_bam,
      normal_bam = normal_bam
  }

  output {
    File manifest = pair_manifest.manifest
  }
}

task pair_manifest {
  input {
    String patient_id
    File tumor_bam
    File normal_bam
  }

  command <<<
    cat <<EOF > ~{patient_id}.pair.tsv
    patient_id	tumor_bam	normal_bam
    ~{patient_id}	~{tumor_bam}	~{normal_bam}
    EOF
  >>>

  output {
    File manifest = "~{patient_id}.pair.tsv"
  }

  runtime {
    cpu: 1
    memory: "1G"
  }
}
