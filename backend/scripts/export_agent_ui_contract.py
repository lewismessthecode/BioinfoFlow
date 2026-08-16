"""Export the stable Agent UI protocol as deterministic JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from app.services.agent_ui.contracts import AgentUiContractBundle


def render_contract() -> str:
    return json.dumps(
        AgentUiContractBundle.model_json_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--check", type=Path, metavar="PATH")
    args = parser.parse_args(argv)
    if (args.output is None) == (args.check is None):
        parser.error("provide either an output path or --check PATH")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rendered = render_contract()
    if args.check is not None:
        committed = (
            args.check.read_text(encoding="utf-8")
            if args.check.exists()
            else None
        )
        if committed == rendered:
            return 0
        print(
            f"Contract drift detected for {args.check}. Regenerate it with: "
            f"python scripts/{Path(__file__).name} {args.check}",
            file=sys.stderr,
        )
        return 1
    assert args.output is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
