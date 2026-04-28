from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy

from app.engine.backend import EngineEvent, EngineEventType, ExecutionBackend

_STREAM_DONE = object()
_ENGINE_LOGS_KEY = "__engine_logs__"
_TERMINAL_EVENT_TYPES = {
    EngineEventType.ERROR,
    EngineEventType.COMPLETED,
}


class LocalBackend(ExecutionBackend):
    async def submit(self, adapter, config: dict, workspace: str):
        prepared_config = deepcopy(config) if isinstance(config, dict) else {}
        required_images = _required_images(prepared_config)
        if required_images:
            yield EngineEvent(
                EngineEventType.LOG,
                {
                    "level": "info",
                    "message": "Preparing required container images: "
                    + ", ".join(required_images),
                },
            )
        prepared_config = await adapter.pre_submit(prepared_config, workspace)

        bootstrap_logs = prepared_config.pop(_ENGINE_LOGS_KEY, [])
        for log in bootstrap_logs:
            yield EngineEvent(
                EngineEventType.LOG,
                {"level": "info", **dict(log)},
            )

        command = await adapter.build_command(prepared_config, workspace)

        process = None
        tasks: list[asyncio.Task] = []
        stderr_lines: list[str] = []
        exhausted = False
        had_terminal_event = False

        try:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workspace,
                )
            except FileNotFoundError:
                yield EngineEvent(
                    EngineEventType.ERROR,
                    {
                        "message": f"{adapter.display_name} binary not found ({adapter.binary})",
                        "exit_code": None,
                    },
                )
                return

            yield EngineEvent(
                EngineEventType.PROCESS_INFO,
                {"pid": process.pid, "engine": adapter.engine_name},
            )

            queue: asyncio.Queue[EngineEvent | object] = asyncio.Queue()

            async def _drain_stream(stream, kind: str) -> None:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode().strip()
                    if kind == "stderr" and text:
                        stderr_lines.append(text)
                    event = adapter.parse_event(text, kind)
                    if event is not None:
                        await queue.put(event)
                await queue.put(_STREAM_DONE)

            tasks = [
                asyncio.create_task(_drain_stream(process.stdout, "stdout")),
                asyncio.create_task(_drain_stream(process.stderr, "stderr")),
            ]

            done_streams = 0
            while done_streams < len(tasks):
                item = await queue.get()
                if item is _STREAM_DONE:
                    done_streams += 1
                    continue

                event = item
                if event.type in _TERMINAL_EVENT_TYPES:
                    had_terminal_event = True
                yield event

            await asyncio.gather(*tasks, return_exceptions=True)
            await process.wait()

            if process.returncode != 0:
                # Exit code is authoritative. Even if a COMPLETED event was
                # parsed from stdout earlier, a non-zero exit means the engine
                # failed — never report that as success.
                yield EngineEvent(
                    EngineEventType.ERROR,
                    {
                        "message": _stderr_tail(stderr_lines)
                        or f"{adapter.display_name} execution failed",
                        "exit_code": process.returncode,
                        "code": "ENGINE_NONZERO_EXIT",
                    },
                )
                return

            await adapter.post_complete(prepared_config, workspace, "completed")

            if not had_terminal_event:
                yield EngineEvent(EngineEventType.COMPLETED, {"success": True})

            exhausted = True
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            if not exhausted and process is not None and process.returncode is None:
                with suppress(Exception):
                    await adapter.cancel(pid=process.pid)
                with suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=1)

    async def cancel(self, adapter, *, pid: int | None, **kwargs) -> bool:
        return await adapter.cancel(pid=pid, **kwargs)


def _stderr_tail(lines: list[str]) -> str:
    return "\n".join(lines[-100:]).strip()


def _required_images(config: dict) -> list[str]:
    runtime = config.get("runtime")
    if not isinstance(runtime, dict):
        return []
    images = runtime.get("required_images")
    if not isinstance(images, list):
        return []
    return [image.strip() for image in images if isinstance(image, str) and image.strip()]
