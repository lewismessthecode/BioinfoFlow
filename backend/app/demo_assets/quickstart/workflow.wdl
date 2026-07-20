version 1.0

workflow bioinfoflow_quickstart {
  input {
    File samples_tsv
    File sample_a_fastq
    File sample_b_fastq
  }

  call summarize_reads {
    input:
      samples_tsv = samples_tsv,
      sample_a_fastq = sample_a_fastq,
      sample_b_fastq = sample_b_fastq
  }

  call render_report {
    input:
      summary_tsv = summarize_reads.summary_tsv
  }

  output {
    File summary_tsv = summarize_reads.summary_tsv
    File report = render_report.report
  }
}

task summarize_reads {
  input {
    File samples_tsv
    File sample_a_fastq
    File sample_b_fastq
  }

  command <<<
    set -eu
    sheet="~{samples_tsv}"
    sample_a="~{sample_a_fastq}"
    sample_b="~{sample_b_fastq}"
    sample_a_name=$(basename "$sample_a")
    sample_b_name=$(basename "$sample_b")

    awk -F '\t' -v sample_a="$sample_a_name" -v sample_b="$sample_b_name" '
      NR == 1 {
        if ($1 != "sample" || $2 != "fastq" || NF != 2) invalid = 1
        next
      }
      {
        rows += 1
        if (NF != 2 || $1 == "" || $2 == "") invalid = 1
        if ($2 == sample_a) seen_a += 1
        else if ($2 == sample_b) seen_b += 1
        else invalid = 1
      }
      END {
        if (invalid || rows != 2 || seen_a != 1 || seen_b != 1) {
          print "samples.tsv must reference each bundled FASTQ basename exactly once" > "/dev/stderr"
          exit 2
        }
      }
    ' "$sheet"

    printf 'sample\treads\tbases\n' > summary.tsv
    tab=$(printf '\t')
    while IFS="$tab" read -r sample fastq; do
      if [ "$sample" = "sample" ] && [ "$fastq" = "fastq" ]; then
        continue
      fi
      case "$fastq" in
        "$sample_a_name") fastq_path="$sample_a" ;;
        "$sample_b_name") fastq_path="$sample_b" ;;
        *)
          echo "samples.tsv must reference each bundled FASTQ basename exactly once" >&2
          exit 2
          ;;
      esac
      awk -v sample="$sample" 'NR % 4 == 2 { reads += 1; bases += length($0) } END { printf "%s\t%d\t%d\n", sample, reads, bases }' "$fastq_path" >> summary.tsv
    done < "$sheet"
  >>>

  output {
    File summary_tsv = "summary.tsv"
  }

  runtime {
    docker: "bash:5.3.15@sha256:a19c811ee9e97fa8a080001d82b8e0ded303f0795cffdb1cbd162731bc8ce208"
  }
}

task render_report {
  input {
    File summary_tsv
  }

  command <<<
    set -eu
    awk -F '\t' 'BEGIN { samples = 0; reads = 0; bases = 0 } NR > 1 { samples += 1; reads += $2; bases += $3 } END { printf "# Bioinfoflow Quickstart Report\n\nSamples: %d\nTotal reads: %d\nTotal bases: %d\n", samples, reads, bases }' "~{summary_tsv}" > report.md
  >>>

  output {
    File report = "report.md"
  }

  runtime {
    docker: "bash:5.3.15@sha256:a19c811ee9e97fa8a080001d82b8e0ded303f0795cffdb1cbd162731bc8ce208"
  }
}
