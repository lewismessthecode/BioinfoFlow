"""Shared async helpers for CLI commands — DRY wrappers around ApiClient."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.cli.context import CliContext
from app.cli.types import ApiResponse


async def api_get(
    ctx: CliContext, path: str, params: dict[str, Any] | None = None
) -> ApiResponse:
    return await ctx.client.get(path, params)


async def api_post(
    ctx: CliContext, path: str, json: dict[str, Any] | None = None
) -> ApiResponse:
    return await ctx.client.post(path, json)


async def api_patch(
    ctx: CliContext, path: str, json: dict[str, Any] | None = None
) -> ApiResponse:
    return await ctx.client.patch(path, json)


async def api_delete(
    ctx: CliContext, path: str, params: dict[str, Any] | None = None
) -> ApiResponse:
    return await ctx.client.delete(path, params)


async def api_upload(
    ctx: CliContext,
    path: str,
    file_path: Path,
    fields: dict[str, str] | None = None,
) -> ApiResponse:
    return await ctx.client.upload(path, file_path, fields)


async def api_download(
    ctx: CliContext, path: str, dest: Path, params: dict[str, Any] | None = None
) -> Path:
    return await ctx.client.download(path, dest, params)
