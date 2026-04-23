nextflow.enable.dsl=2

process WRITE_HELLO {
  publishDir params.outdir, mode: 'copy'

  output:
  path "hello.txt"

  script:
  '''
  echo "hello from e2e" > hello.txt
  '''
}

workflow {
  WRITE_HELLO()
}
