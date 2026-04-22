version 1.0

workflow resource_stress_mini {
    input {
        String outdir
        Int fanout = 30
        Int sleep_seconds = 5
    }

    meta {
        pipeline_version: "1.0.0"
        description: "Large scatter fanout to stress scheduler backpressure, SSE volume, and DAG render."
    }

    call PREP {
        input:
            outdir = outdir,
            fanout = fanout
    }

    scatter (seed in read_lines(PREP.seeds)) {
        call BUSY {
            input:
                outdir = outdir,
                seed = seed,
                sleep_seconds = sleep_seconds
        }
    }

    call REDUCE {
        input:
            outdir = outdir,
            done_markers = BUSY.marker
    }

    output {
        File summary = REDUCE.summary
    }
}

task PREP {
    input {
        String outdir
        Int fanout
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/01.prep
        # Generate N seed lines; scatter will read each line as a String.
        awk -v n=~{fanout} 'BEGIN { for (i = 1; i <= n; i++) printf "seed-%03d\n", i }' \
            > ~{outdir}/01.prep/seeds.txt
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
        File seeds = "${outdir}/01.prep/seeds.txt"
    }
}

task BUSY {
    input {
        String outdir
        String seed
        Int sleep_seconds
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/02.busy
        echo "BUSY start ~{seed} sleep=~{sleep_seconds} at $(date -Iseconds)"
        sleep ~{sleep_seconds}
        echo "BUSY done ~{seed} at $(date -Iseconds)" > ~{outdir}/02.busy/~{seed}.done
    >>>

    runtime {
        cpu: 1
        memory: "256M"
        docker: "ubuntu:22.04"
        disks: "20MB"
    }

    meta {
        compute_type: "cpu"
        timeout: "10m"
    }

    output {
        File marker = "${outdir}/02.busy/${seed}.done"
    }
}

task REDUCE {
    input {
        String outdir
        Array[File] done_markers
    }

    command <<<
        set -e
        mkdir -p ~{outdir}/03.reduce
        count=0
        for f in ~{sep=" " done_markers}; do
            count=$((count + 1))
        done
        cat > ~{outdir}/03.reduce/summary.txt <<EOF
run_finished=$(date -Iseconds)
markers_received=$count
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
        File summary = "${outdir}/03.reduce/summary.txt"
    }
}
