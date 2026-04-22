"""Parse Nextflow trace files to extract task execution information."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.utils.dag_builder import clean_process_label
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TraceTask:
    """Represents a single task from a Nextflow trace file."""

    task_id: int
    hash: str
    native_id: str
    name: str  # e.g., "FASTQC (sample1)"
    process_name: str  # e.g., "FASTQC"
    status: str  # COMPLETED, FAILED, RUNNING, CACHED
    exit_code: int | None
    duration: str | None = None
    realtime: str | None = None
    cpu_percent: float | None = None
    peak_rss: str | None = None


# Nextflow status -> Frontend status mapping
STATUS_MAP: dict[str, str] = {
    "COMPLETED": "success",
    "CACHED": "success",
    "FAILED": "failed",
    "ABORTED": "failed",
    "RUNNING": "running",
    "SUBMITTED": "running",
    "PENDING": "pending",
}


class TraceParser:
    """Parse Nextflow trace TSV files."""

    def parse_trace_file(self, trace_path: str | Path) -> list[TraceTask]:
        """Parse a Nextflow trace file and return list of tasks.

        Args:
            trace_path: Path to the trace TSV file

        Returns:
            List of TraceTask objects
        """
        trace_path = Path(trace_path)
        if not trace_path.exists():
            logger.warning("trace.file_not_found", path=str(trace_path))
            return []

        tasks: list[TraceTask] = []
        try:
            with trace_path.open("r", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    task = self._parse_row(row)
                    if task:
                        tasks.append(task)
        except Exception as e:
            logger.error("trace.parse_error", path=str(trace_path), error=str(e))
            return []

        logger.info("trace.parsed", path=str(trace_path), task_count=len(tasks))
        return tasks

    def _parse_row(self, row: dict[str, str]) -> TraceTask | None:
        """Parse a single row from the trace file."""
        try:
            name = row.get("name", "")
            process_name = self._extract_process_name(name)

            task_id_str = row.get("task_id", "")
            task_id = int(task_id_str) if task_id_str else 0

            exit_str = row.get("exit", "")
            exit_code = int(exit_str) if exit_str and exit_str != "-" else None

            cpu_str = row.get("%cpu", "")
            cpu_percent = float(cpu_str) if cpu_str and cpu_str != "-" else None

            return TraceTask(
                task_id=task_id,
                hash=row.get("hash", ""),
                native_id=row.get("native_id", ""),
                name=name,
                process_name=process_name,
                status=row.get("status", ""),
                exit_code=exit_code,
                duration=row.get("duration") or None,
                realtime=row.get("realtime") or None,
                cpu_percent=cpu_percent,
                peak_rss=row.get("peak_rss") or None,
            )
        except (ValueError, KeyError) as e:
            logger.warning("trace.row_parse_error", error=str(e), row=row)
            return None

    def _extract_process_name(self, full_name: str) -> str:
        """Extract process name from full task name.

        Examples:
            "FASTQC (sample1)" -> "FASTQC"
            "MULTIQC" -> "MULTIQC"
            "nf-core/viralrecon:FASTQC" -> "FASTQC"
        """
        return clean_process_label(full_name).upper()

    def map_status(self, nf_status: str) -> str:
        """Map Nextflow status to frontend status.

        Args:
            nf_status: Nextflow status (COMPLETED, FAILED, RUNNING, etc.)

        Returns:
            Frontend status (success, failed, running, pending)
        """
        return STATUS_MAP.get(nf_status.upper(), "pending")

    def iter_tasks(self, trace_path: str | Path) -> Iterator[TraceTask]:
        """Iterate over tasks in a trace file (memory efficient).

        Args:
            trace_path: Path to the trace TSV file

        Yields:
            TraceTask objects
        """
        trace_path = Path(trace_path)
        if not trace_path.exists():
            return

        with trace_path.open("r", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                task = self._parse_row(row)
                if task:
                    yield task

    def get_process_statuses(self, trace_path: str | Path) -> dict[str, str]:
        """Get a mapping of process names to their latest status.

        If a process has multiple tasks (e.g., parallel execution),
        the status priority is: running > failed > success > pending

        Args:
            trace_path: Path to the trace TSV file

        Returns:
            Dict mapping process name to frontend status
        """
        process_statuses: dict[str, str] = {}
        priority = {"running": 3, "failed": 2, "success": 1, "pending": 0}

        for task in self.iter_tasks(trace_path):
            status = self.map_status(task.status)
            current = process_statuses.get(task.process_name)

            if current is None or priority.get(status, 0) > priority.get(current, 0):
                process_statuses[task.process_name] = status

        return process_statuses
