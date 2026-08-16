from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Iterable
from typing import Literal, Mapping, TypeAlias


EnvironmentKind: TypeAlias = Literal["local", "ssh"]
EnvironmentStatus: TypeAlias = Literal["online", "offline", "error", "unknown"]
EnvironmentScopeMode: TypeAlias = Literal["auto", "manual"]


class EnvironmentSelectionError(ValueError):
    code = "environment_not_authorized"

    def __init__(self, environment_ids: tuple[str, ...]) -> None:
        self.environment_ids = environment_ids
        joined = ", ".join(environment_ids)
        super().__init__(f"environment selection is not authorized: {joined}")


@dataclass(frozen=True, slots=True)
class EnvironmentDescriptor:
    environment_id: str
    kind: EnvironmentKind
    display_name: str
    description: str | None = None
    status: EnvironmentStatus = "unknown"
    host: str | None = None


@dataclass(frozen=True, slots=True)
class EnvironmentScopeRequest:
    mode: EnvironmentScopeMode
    selected_environment_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedEnvironmentScope:
    mode: EnvironmentScopeMode
    environments: Mapping[str, EnvironmentDescriptor]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "environments",
            MappingProxyType(dict(self.environments)),
        )

    @property
    def environment_ids(self) -> tuple[str, ...]:
        return tuple(self.environments)

    def require(self, environment_id: str) -> EnvironmentDescriptor:
        return self.environments[environment_id]


def resolve_environment_scope(
    request: EnvironmentScopeRequest,
    authorized_environments: Iterable[EnvironmentDescriptor],
) -> ResolvedEnvironmentScope:
    authorized = {
        environment.environment_id: environment
        for environment in authorized_environments
    }
    if request.mode == "auto":
        environments = authorized
    else:
        unknown_ids = tuple(
            environment_id
            for environment_id in request.selected_environment_ids
            if environment_id not in authorized
        )
        if unknown_ids:
            raise EnvironmentSelectionError(unknown_ids)
        environments = {
            environment_id: authorized[environment_id]
            for environment_id in request.selected_environment_ids
        }
    return ResolvedEnvironmentScope(
        mode=request.mode,
        environments=environments,
    )
