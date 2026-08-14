from __future__ import annotations

import shlex


_SHELL_CONTROL_CHARACTERS = frozenset(";&|<>`$\\\n\r\x00")


def scoped_bif_argv(command: object) -> tuple[str, ...] | None:
    """Return argv only when *command* is provably one plain ``bif`` command.

    This is deliberately stricter than the risk classifier. It is a credential
    exposure boundary, so shell composition, expansion, redirection, scripts,
    wrappers and environment assignments are rejected even when they might be
    harmless in a particular invocation.
    """

    if not isinstance(command, str) or not command.strip():
        return None
    if any(character in command for character in _SHELL_CONTROL_CHARACTERS):
        return None
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError:
        return None
    if not argv or argv[0] != "bif":
        return None
    if any(
        argument == "--base-url" or argument.startswith("--base-url=")
        for argument in argv[1:]
    ):
        return None
    return argv


def is_scoped_bif_command(command: object) -> bool:
    return scoped_bif_argv(command) is not None


__all__ = ["is_scoped_bif_command", "scoped_bif_argv"]
