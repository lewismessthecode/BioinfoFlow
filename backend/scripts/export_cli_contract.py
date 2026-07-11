"""Export the visible Typer command tree as deterministic JSON."""

from __future__ import annotations

import argparse
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from click import Argument, Command, Context, Group, Option, Parameter
from typer.main import get_command


def _normalize_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return _normalize_default(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_normalize_default(item) for item in value]
    if isinstance(value, list):
        return [_normalize_default(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_default(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(
        f"unsupported default for deterministic CLI contract: {value!r}"
    )


def _parameter_contract(
    parameter: Parameter,
    context: Context,
) -> dict[str, Any]:
    if isinstance(parameter, Option):
        option_names = [*parameter.opts, *parameter.secondary_opts]
        name = next(
            (option for option in parameter.opts if option.startswith("--")),
            parameter.opts[0],
        )
        aliases = [option for option in option_names if option != name]
        kind = "option"
        count = parameter.count
        flag_value = (
            _normalize_default(parameter.flag_value) if parameter.is_flag else None
        )
        is_flag = parameter.is_flag
        multiple = parameter.multiple
    elif isinstance(parameter, Argument):
        name = parameter.human_readable_name
        aliases = []
        kind = "argument"
        count = False
        flag_value = None
        is_flag = False
        multiple = False
    else:
        raise TypeError(f"unsupported Click parameter: {parameter!r}")

    return {
        "aliases": aliases,
        "count": count,
        "default": _normalize_default(parameter.default),
        "envvar": _normalize_default(parameter.envvar),
        "flag_value": flag_value,
        "help": getattr(parameter, "help", None),
        "is_eager": parameter.is_eager,
        "is_flag": is_flag,
        "kind": kind,
        "metavar": parameter.make_metavar(context),
        "multiple": multiple,
        "name": name,
        "nargs": parameter.nargs,
        "required": parameter.required,
        "type": _normalize_default(parameter.type.to_info_dict()),
    }


def _command_contract(
    command: Command,
    path: tuple[str, ...],
    parent_context: Context | None = None,
) -> dict[str, Any]:
    context = Context(
        command,
        info_name=path[-1],
        parent=parent_context,
        **command.context_settings,
    )
    visible_parameters = [
        _parameter_contract(parameter, context)
        for parameter in command.params
        if not parameter.hidden
    ]
    visible_commands: list[dict[str, Any]] = []
    if isinstance(command, Group):
        visible_commands = [
            _command_contract(child, (*path, name), context)
            for name, child in sorted(command.commands.items())
            if not child.hidden
        ]

    return {
        "allow_extra_args": context.allow_extra_args,
        "allow_interspersed_args": context.allow_interspersed_args,
        "chain": bool(getattr(command, "chain", False)),
        "commands": visible_commands,
        "help": command.help,
        "help_option_names": (
            list(context.help_option_names) if command.add_help_option else []
        ),
        "ignore_unknown_options": context.ignore_unknown_options,
        "invoke_without_command": bool(
            getattr(command, "invoke_without_command", False)
        ),
        "name": path[-1],
        "no_args_is_help": bool(getattr(command, "no_args_is_help", False)),
        "parameters": visible_parameters,
        "path": " ".join(path),
    }


def build_contract() -> dict[str, Any]:
    """Return the visible command tree without invoking any CLI callback."""
    from app.cli.main import app

    root_command = get_command(app)
    root_name = root_command.name or "bif"
    return {
        "command": _command_contract(root_command, (root_name,)),
        "schema_version": 1,
    }


def render_contract() -> str:
    return json.dumps(
        build_contract(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Path to write the generated CLI contract.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        metavar="PATH",
        help="Fail if PATH does not match the generated CLI contract.",
    )
    args = parser.parse_args(argv)
    if (args.output is None) == (args.check is None):
        parser.error("provide either an output path or --check PATH")
    return args


def _check_contract(path: Path, rendered: str) -> int:
    try:
        committed = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        committed = None

    if committed == rendered:
        return 0

    print(
        f"Contract drift detected for {path}. "
        f"Regenerate it with: python scripts/{Path(__file__).name} {path}",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rendered = render_contract()

    if args.check is not None:
        return _check_contract(args.check, rendered)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
