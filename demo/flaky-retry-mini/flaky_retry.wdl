version 1.0

workflow flaky_retry_mini {
    input {
        String outdir
        Int flaky_count = 2
        Boolean fatal_enabled = false
    }

    meta {
        pipeline_version: "1.0.0"
        description: "Exercises maxRetries, failure propagation, and downstream skip."
    }

    call PREP {
        input:
            outdir = outdir
    }

    call FLAKY {
        input:
            outdir = outdir,
            flaky_count = flaky_count,
            PREP_DONE = PREP.PREP_DONE
    }

    call FATAL {
        input:
            outdir = outdir,
            fatal_enabled = fatal_enabled,
            FLAKY_DONE = FLAKY.FLAKY_DONE
    }

    call CLEANUP {
        input:
            outdir = outdir,
            FATAL_DONE = FATAL.FATAL_DONE
    }

    output {
        File summary = CLEANUP.summary
    }
}

task PREP {
    input {
        String outdir
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/01.prep
        echo "run_started=$(date -Iseconds)" > ~{outdir}/01.prep/state.txt
        # Reset the per-run attempt counter. FLAKY will append one line per attempt.
        : > ~{outdir}/01.prep/flaky_attempts.txt
        echo "done" > ~{outdir}/01.prep/done.marker
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "5m"
    }

    output {
        String PREP_DONE = "DONE"
    }
}

task FLAKY {
    input {
        String outdir
        Int flaky_count
        String PREP_DONE
    }

    command <<<
        set -e
        # Append one line per attempt to a persistent counter file under outdir.
        # When attempts_so_far < flaky_count, exit non-zero so the scheduler retries.
        # When attempts_so_far == flaky_count, finish successfully.
        echo "attempt=$(date -Iseconds)" >> ~{outdir}/01.prep/flaky_attempts.txt
        attempts_so_far=$(wc -l < ~{outdir}/01.prep/flaky_attempts.txt | tr -d ' ')
        echo "FLAKY attempt number=$attempts_so_far target=~{flaky_count}"
        if [ "$attempts_so_far" -lt "~{flaky_count}" ]; then
            echo "FLAKY intentional failure at attempt $attempts_so_far" >&2
            exit 1
        fi
        mkdir -p ~{outdir}/02.flaky
        echo "attempts=$attempts_so_far" > ~{outdir}/02.flaky/result.txt
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        maxRetries: 3
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "5m"
    }

    output {
        String FLAKY_DONE = "DONE"
    }
}

task FATAL {
    input {
        String outdir
        Boolean fatal_enabled
        String FLAKY_DONE
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/03.fatal
        if [ "~{fatal_enabled}" = "true" ]; then
            echo "FATAL fatal_enabled=true, exiting 1" >&2
            exit 1
        fi
        echo "skipped" > ~{outdir}/03.fatal/state.txt
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "5m"
    }

    output {
        String FATAL_DONE = "DONE"
    }
}

task CLEANUP {
    input {
        String outdir
        String FATAL_DONE
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/04.cleanup
        attempts_file=~{outdir}/01.prep/flaky_attempts.txt
        attempts=$(wc -l < "$attempts_file" 2>/dev/null | tr -d ' ' || echo "0")
        cat > ~{outdir}/04.cleanup/summary.txt <<EOF
run_finished=$(date -Iseconds)
flaky_attempts=$attempts
fatal_state=$(cat ~{outdir}/03.fatal/state.txt 2>/dev/null || echo "unknown")
EOF
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "5m"
    }

    output {
        File summary = "${outdir}/04.cleanup/summary.txt"
    }
}
