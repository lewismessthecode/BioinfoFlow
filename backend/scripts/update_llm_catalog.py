from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import urlopen


SOURCE_IDS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "fireworks": "fireworks-ai",
    "qwen": "alibaba-cn",
    "deepseek": "deepseek",
    "xai": "xai",
    "zai": "zai",
    "kimi-code": "kimi-for-coding",
    "minimax": "minimax",
    "huggingface": "huggingface",
    "gemini": "google",
}

OUTPUT = Path(__file__).parents[1] / "app/services/llm/catalog_snapshot.json"


def _load_source(input_path: Path | None) -> dict:
    if input_path is not None:
        return json.loads(input_path.read_text(encoding="utf-8"))
    with urlopen("https://models.dev/api.json", timeout=30) as response:  # noqa: S310
        return json.load(response)


def _normalize_model(model: dict) -> dict:
    modalities = model.get("modalities") or {}
    limits = model.get("limit") or {}
    return {
        "id": model["id"],
        "name": model.get("name") or model["id"],
        "context_length": limits.get("context"),
        "max_output_tokens": limits.get("output"),
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": "image" in (modalities.get("input") or []),
        "supports_json_schema": bool(model.get("structured_output")),
        "supports_reasoning": bool(model.get("reasoning")),
        "output_modalities": ["text"],
    }


def build_snapshot(source: dict) -> dict:
    providers: dict[str, list[dict]] = {}
    for provider_id, source_id in SOURCE_IDS.items():
        source_models = source[source_id]["models"].values()
        eligible = [
            model
            for model in source_models
            if model.get("tool_call") is True
            and (model.get("modalities") or {}).get("output") == ["text"]
        ]
        if provider_id != "kimi-code":
            eligible = sorted(
                eligible,
                key=lambda model: (
                    model.get("last_updated") or model.get("release_date") or "",
                    model["id"],
                ),
                reverse=True,
            )[:50]
        models = [_normalize_model(model) for model in eligible]
        providers[provider_id] = sorted(models, key=lambda item: item["id"])
    return {
        "schema_version": 1,
        "source": "https://models.dev/api.json",
        "providers": providers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    snapshot = build_snapshot(_load_source(args.input))
    args.output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
