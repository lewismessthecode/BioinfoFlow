from __future__ import annotations

from app.engine.backend import EngineEvent, EngineEventType


def test_engine_event_properties_expose_common_fields():
    event = EngineEvent(
        EngineEventType.TASK_UPDATE,
        {
            "message": "task started",
            "name": "FASTQC",
            "status": "running",
            "pid": 321,
            "exit_code": 7,
        },
    )

    assert event.message == "task started"
    assert event.task_name == "FASTQC"
    assert event.task_status == "running"
    assert event.pid == 321
    assert event.exit_code == 7
