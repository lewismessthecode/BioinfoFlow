from __future__ import annotations

from copy import deepcopy
from typing import Any


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return deepcopy(value)
    return {}


class RunConfigHelper:
    """Type-safe accessors for the Run.config JSON field."""

    def __init__(self, config: dict | None):
        self._config = _as_dict(config)

    @property
    def version(self) -> int:
        return int(self._config.get("config_schema_version", 0) or 0)

    @property
    def params(self) -> dict:
        request = _as_dict(self._config.get("request"))
        return _as_dict(request.get("params")) or _as_dict(self._config.get("params"))

    @property
    def inputs(self) -> dict:
        request = _as_dict(self._config.get("request"))
        return _as_dict(request.get("inputs")) or _as_dict(self._config.get("inputs"))

    @property
    def config_overrides(self) -> dict:
        request = _as_dict(self._config.get("request"))
        return _as_dict(request.get("config_overrides")) or _as_dict(
            self._config.get("config_overrides")
        )

    @property
    def resolved_runspec(self) -> dict:
        resolved = _as_dict(self._config.get("resolved"))
        return _as_dict(resolved.get("runspec")) or _as_dict(
            self._config.get("resolved_runspec")
        )

    @property
    def runtime(self) -> dict:
        return _as_dict(self._config.get("runtime"))

    @property
    def pid(self) -> int | None:
        pid = self.runtime.get("pid")
        return pid if isinstance(pid, int) else None

    @property
    def engine(self) -> str | None:
        engine = self.runtime.get("engine")
        return str(engine) if engine is not None else None

    @property
    def session_id(self) -> str | None:
        session_id = self.runtime.get("session_id")
        return str(session_id) if session_id else None

    @property
    def resume_token(self) -> str | None:
        runtime = self.runtime
        token = runtime.get("resume_token") or runtime.get("resume_from")
        return str(token) if token else None

    @property
    def timeout_seconds(self) -> int | None:
        policy = _as_dict(self._config.get("policy"))
        timeout = policy.get("timeout_seconds")
        return int(timeout) if isinstance(timeout, int) else None

    @property
    def retry_policy(self) -> dict:
        policy = _as_dict(self._config.get("policy"))
        return _as_dict(policy.get("retry"))

    @property
    def dag(self) -> dict:
        ui = _as_dict(self._config.get("ui"))
        return _as_dict(ui.get("dag")) or _as_dict(
            self._config.get("dag", {"nodes": [], "edges": []})
        )

    def to_dict(self) -> dict:
        return _as_dict(self._config)

    @staticmethod
    def build_v1(
        *,
        params: dict | None,
        inputs: dict | None,
        config_overrides: dict | None,
        resolved_runspec: dict | None = None,
        retry_policy: dict | None = None,
        timeout_seconds: int | None = None,
    ) -> dict:
        params_payload = _as_dict(params)
        inputs_payload = _as_dict(inputs)
        overrides_payload = _as_dict(config_overrides)
        resolved_payload = _as_dict(resolved_runspec)
        policy_payload = {}
        retry_payload = _as_dict(retry_policy)
        if retry_payload:
            policy_payload["retry"] = retry_payload
        if isinstance(timeout_seconds, int):
            policy_payload["timeout_seconds"] = timeout_seconds

        return {
            "config_schema_version": 1,
            "request": {
                "params": params_payload,
                "inputs": inputs_payload,
                "config_overrides": overrides_payload,
            },
            "resolved": {
                "runspec": resolved_payload,
            },
            "runtime": {},
            "policy": policy_payload,
            "ui": {"dag": {}},
            # Preserve the current flat contract during the phase-0 migration.
            "params": params_payload,
            "inputs": inputs_payload,
            "config_overrides": overrides_payload,
            "resolved_runspec": resolved_payload,
        }
