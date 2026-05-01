"""CLI configuration store — reads/writes ~/.config/bioinfoflow/cli.toml."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w


_DEFAULT_CONFIG_DIR = Path("~/.config/bioinfoflow").expanduser()
_CONFIG_FILENAME = "cli.toml"

_DEFAULTS: dict[str, str] = {
    "mode": "auto",
    "base_url": "http://localhost:8000/api/v1",
    "output": "human",
}


class ConfigStore:
    """Manage persistent CLI configuration in a TOML file."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or _DEFAULT_CONFIG_DIR
        self._path = self._dir / _CONFIG_FILENAME
        self._cache: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            return {}
        self._cache = tomllib.loads(self._path.read_text())
        return self._cache

    def save(self, data: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(tomli_w.dumps(data).encode())
        os.chmod(self._path, 0o600)
        self._cache = None

    def get(self, key: str) -> str | None:
        return self.load().get(key)

    def set(self, key: str, value: str) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def unset(self, key: str) -> bool:
        """Remove a key. Return True if it existed, False otherwise."""
        data = self.load()
        if key not in data:
            return False
        del data[key]
        self.save(data)
        return True

    def init(self) -> None:
        """Create config directory and default config file."""
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)
        if not self._path.exists():
            self.save(dict(_DEFAULTS))

    def resolve(self, key: str, cli_value: str | None, env_key: str) -> str | None:
        """Resolve a value with priority: CLI flag > env var > config file > default."""
        if cli_value is not None:
            return cli_value
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
        stored = self.get(key)
        if stored is not None:
            return stored
        return _DEFAULTS.get(key)
