from __future__ import annotations

from app.services.trace_parser import TraceParser


def test_parse_trace_file_reads_tasks_and_normalizes_process_names(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "task_id\thash\tnative_id\tname\tstatus\texit\tduration\trealtime\t%cpu\tpeak_rss\n"
        "1\tabc\t1001\tnf-core/viralrecon:FASTQC (sample1)\tCOMPLETED\t0\t1m\t30s\t87.5\t1 GB\n"
        "2\tdef\t1002\tMULTIQC\tRUNNING\t-\t2m\t90s\t-\t2 GB\n",
        encoding="utf-8",
    )

    parser = TraceParser()
    tasks = parser.parse_trace_file(trace_path)

    assert len(tasks) == 2
    assert tasks[0].task_id == 1
    assert tasks[0].process_name == "FASTQC"
    assert tasks[0].exit_code == 0
    assert tasks[0].cpu_percent == 87.5
    assert tasks[1].process_name == "MULTIQC"
    assert tasks[1].exit_code is None
    assert tasks[1].cpu_percent is None


def test_parse_trace_file_returns_empty_list_for_missing_or_invalid_rows(tmp_path):
    parser = TraceParser()

    assert parser.parse_trace_file(tmp_path / "missing.trace") == []

    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "task_id\thash\tnative_id\tname\tstatus\texit\t%cpu\n"
        "bad-id\tabc\t1001\tFASTQC\tCOMPLETED\t0\t85.1\n"
        "2\tdef\t1002\tALIGN\tFAILED\t1\t22.5\n",
        encoding="utf-8",
    )

    tasks = parser.parse_trace_file(trace_path)
    assert len(tasks) == 1
    assert tasks[0].task_id == 2
    assert tasks[0].process_name == "ALIGN"


def test_get_process_statuses_uses_highest_priority_status(tmp_path):
    trace_path = tmp_path / "trace.txt"
    trace_path.write_text(
        "task_id\thash\tnative_id\tname\tstatus\texit\t%cpu\n"
        "1\ta\t1001\tFASTQC\tCOMPLETED\t0\t75\n"
        "2\tb\t1002\tFASTQC\tRUNNING\t-\t12\n"
        "3\tc\t1003\tALIGN\tFAILED\t1\t33\n"
        "4\td\t1004\tALIGN\tCACHED\t0\t44\n"
        "5\te\t1005\tMULTIQC\tSUBMITTED\t-\t-\n",
        encoding="utf-8",
    )

    parser = TraceParser()

    assert parser.get_process_statuses(trace_path) == {
        "FASTQC": "running",
        "ALIGN": "failed",
        "MULTIQC": "running",
    }
