"""Background command execution manager (s08 pattern).

Runs shell commands in daemon threads and collects results via a
thread-safe notification queue for between-turn draining in the agent loop.
"""

from __future__ import annotations

import queue
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_OUTPUT_CHARS = 10_000


@dataclass
class BackgroundResult:
    """Result of a completed background command."""

    task_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class BackgroundManager:
    """Manages background shell command execution with async notification."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        timeout: int = 300,
    ) -> None:
        self._workspace = workspace_root
        self._timeout = timeout
        self._results: queue.Queue[BackgroundResult] = queue.Queue()
        self._next_id = 1
        self._active: int = 0
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._shutdown_event = threading.Event()

    def spawn(self, command: str) -> str:
        """Launch a command in a background thread. Returns a task_id."""
        with self._lock:
            task_id = f"bg-{self._next_id}"
            self._next_id += 1
            self._active += 1

        def _run() -> None:
            start = time.monotonic()
            exit_code = -1
            stdout = ""
            stderr = ""
            try:
                result = subprocess.run(
                    shlex.split(command),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=str(self._workspace) if self._workspace else None,
                )
                exit_code = result.returncode
                stdout = result.stdout[:MAX_OUTPUT_CHARS]
                stderr = result.stderr[:MAX_OUTPUT_CHARS]
            except subprocess.TimeoutExpired:
                stderr = f"Command timed out after {self._timeout}s"
            except Exception as exc:
                stderr = str(exc)
            finally:
                elapsed = time.monotonic() - start
                self._results.put(
                    BackgroundResult(
                        task_id=task_id,
                        command=command,
                        exit_code=exit_code,
                        stdout=stdout,
                        stderr=stderr,
                        elapsed_seconds=round(elapsed, 2),
                    )
                )
                with self._lock:
                    self._active -= 1

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        with self._lock:
            self._threads.append(thread)
        logger.info("background.spawned", task_id=task_id, command=command[:80])
        return task_id

    def drain_notifications(self) -> list[BackgroundResult]:
        """Non-blocking drain of all completed results."""
        results: list[BackgroundResult] = []
        while True:
            try:
                results.append(self._results.get_nowait())
            except queue.Empty:
                break
        return results

    def active_count(self) -> int:
        """Return the number of currently running background tasks."""
        with self._lock:
            return self._active

    def shutdown(self, timeout: float = 5.0) -> None:
        """Signal workers to stop and join all threads with a timeout."""
        self._shutdown_event.set()
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=timeout)
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
        logger.info("background.shutdown", remaining_threads=len(self._threads))
