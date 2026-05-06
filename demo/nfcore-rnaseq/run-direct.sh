#!/usr/bin/env bash
set -euo pipefail

PIPELINE="nf-core/rnaseq"
PIPELINE_VERSION="3.24.0"
PROFILE="test,docker"
TEST_DATA_REV="626c8fab639062eade4b10747e919341cbf9b41a"
SAMPLESHEET_URL="https://raw.githubusercontent.com/nf-core/test-datasets/${TEST_DATA_REV}/samplesheet/v3.10/samplesheet_test.csv"
REFERENCE_BASE_URL="https://raw.githubusercontent.com/nf-core/test-datasets/${TEST_DATA_REV}/reference"
KRAKEN_DB_URL="https://raw.githubusercontent.com/nf-core/test-datasets/eb0cbf73c3f103f8aeda9878ba200e92b4d045d8/data/genomics/sarscov2/genome/db/kraken2.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ROOT="${SCRIPT_DIR}/runs/direct-test-docker"
WORK_DIR="${RUN_ROOT}/work"
OUT_DIR="${RUN_ROOT}/results"
CONFIG_FILE="${SCRIPT_DIR}/nextflow.test-docker.config"
TESTDATA_DIR="${RUN_ROOT}/testdata"
REFERENCE_DIR="${TESTDATA_DIR}/reference"
FASTQ_DIR="${TESTDATA_DIR}/fastq"
REMOTE_SAMPLESHEET_FILE="${TESTDATA_DIR}/samplesheet_test.remote.csv"
SAMPLESHEET_FILE="${TESTDATA_DIR}/samplesheet_test.local.csv"

mkdir -p "${RUN_ROOT}" "${TESTDATA_DIR}" "${REFERENCE_DIR}" "${FASTQ_DIR}"

if ! command -v nextflow >/dev/null 2>&1; then
  echo "nextflow is required but was not found on PATH." >&2
  exit 127
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but was not found on PATH." >&2
  exit 127
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but was not found on PATH." >&2
  exit 127
fi

fetch() {
  local url="$1"
  local dest="$2"
  if [[ -s "${dest}" ]]; then
    return 0
  fi
  echo "Fetching ${url}" >&2
  curl --fail --location --retry 5 --retry-delay 2 --retry-all-errors \
    "${url}" \
    --output "${dest}"
}

if [[ ! -s "${REMOTE_SAMPLESHEET_FILE}" ]]; then
  echo "Fetching nf-core test samplesheet..."
  fetch "${SAMPLESHEET_URL}" "${REMOTE_SAMPLESHEET_FILE}"
fi

{
  IFS= read -r header
  echo "${header}"
  while IFS=, read -r sample fastq_1 fastq_2 strandedness; do
    local_fastq_1=""
    local_fastq_2=""
    if [[ -n "${fastq_1}" ]]; then
      local_fastq_1="${FASTQ_DIR}/$(basename "${fastq_1}")"
      fetch "${fastq_1}" "${local_fastq_1}"
    fi
    if [[ -n "${fastq_2}" ]]; then
      local_fastq_2="${FASTQ_DIR}/$(basename "${fastq_2}")"
      fetch "${fastq_2}" "${local_fastq_2}"
    fi
    echo "${sample},${local_fastq_1},${local_fastq_2},${strandedness}"
  done
} < "${REMOTE_SAMPLESHEET_FILE}" > "${SAMPLESHEET_FILE}"

fetch "${REFERENCE_BASE_URL}/genome.fasta" "${REFERENCE_DIR}/genome.fasta"
fetch "${REFERENCE_BASE_URL}/genes_with_empty_tid.gtf.gz" "${REFERENCE_DIR}/genes_with_empty_tid.gtf.gz"
fetch "${REFERENCE_BASE_URL}/genes.gff.gz" "${REFERENCE_DIR}/genes.gff.gz"
fetch "${REFERENCE_BASE_URL}/transcriptome.fasta" "${REFERENCE_DIR}/transcriptome.fasta"
fetch "${REFERENCE_BASE_URL}/gfp.fa.gz" "${REFERENCE_DIR}/gfp.fa.gz"
fetch "${REFERENCE_BASE_URL}/bbsplit_fasta_list.txt" "${REFERENCE_DIR}/bbsplit_fasta_list.txt"
fetch "${REFERENCE_BASE_URL}/hisat2.tar.gz" "${REFERENCE_DIR}/hisat2.tar.gz"
fetch "${REFERENCE_BASE_URL}/salmon.tar.gz" "${REFERENCE_DIR}/salmon.tar.gz"
fetch "${KRAKEN_DB_URL}" "${REFERENCE_DIR}/kraken2.tar.gz"

echo "Running ${PIPELINE}@${PIPELINE_VERSION} with -profile ${PROFILE}"
echo "Run root: ${RUN_ROOT}"

nextflow run "${PIPELINE}" \
  -r "${PIPELINE_VERSION}" \
  -profile "${PROFILE}" \
  -c "${CONFIG_FILE}" \
  -work-dir "${WORK_DIR}" \
  --input "${SAMPLESHEET_FILE}" \
  --fasta "${REFERENCE_DIR}/genome.fasta" \
  --gtf "${REFERENCE_DIR}/genes_with_empty_tid.gtf.gz" \
  --gff "${REFERENCE_DIR}/genes.gff.gz" \
  --transcript_fasta "${REFERENCE_DIR}/transcriptome.fasta" \
  --additional_fasta "${REFERENCE_DIR}/gfp.fa.gz" \
  --bbsplit_fasta_list "${REFERENCE_DIR}/bbsplit_fasta_list.txt" \
  --hisat2_index "${REFERENCE_DIR}/hisat2.tar.gz" \
  --salmon_index "${REFERENCE_DIR}/salmon.tar.gz" \
  --kraken_db "${REFERENCE_DIR}/kraken2.tar.gz" \
  --outdir "${OUT_DIR}"

cat <<EOF

nf-core/rnaseq demo completed.
Results: ${OUT_DIR}
Work dir: ${WORK_DIR}
EOF
