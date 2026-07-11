"""Export the FastAPI OpenAPI document as deterministic JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


def build_contract() -> dict[str, Any]:
    """Return the complete OpenAPI document exposed by the application."""
    from app.main import app

    return app.openapi()


def render_contract() -> str:
    """Serialize the OpenAPI document without changing its semantic content."""
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
        help="Path to write the generated OpenAPI contract.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        metavar="PATH",
        help="Fail if PATH does not match the generated OpenAPI contract.",
    )
    args = parser.parse_args(argv)
    if (args.output is None) == (args.check is None):
        parser.error("provide either an output path or --check PATH")
    return args


def _check_contract(path: Path, rendered: str) -> int:
    try:
        committed = path.read_text()
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
    args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
