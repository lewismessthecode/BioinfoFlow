from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.auth.session import AuthUser, normalize_session_token, validate_session
from app.config import settings


def _create_better_auth_db(db_path: Path) -> None:
    """Create a minimal Better Auth SQLite DB with session and user tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE user (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            emailVerified INTEGER NOT NULL,
            image TEXT,
            role TEXT,
            teamRole TEXT,
            banned INTEGER DEFAULT 0,
            banExpires date,
            createdAt date NOT NULL,
            updatedAt date NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            expiresAt date NOT NULL,
            token TEXT NOT NULL UNIQUE,
            createdAt date NOT NULL,
            updatedAt date NOT NULL,
            ipAddress TEXT,
            userAgent TEXT,
            userId TEXT NOT NULL,
            FOREIGN KEY (userId) REFERENCES user(id)
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_user(
    db_path: Path,
    user_id: str,
    name: str,
    email: str,
    image: str | None = None,
    *,
    role: str = "user",
    team_role: str = "member",
    banned: bool = False,
    ban_expires: datetime | None = None,
) -> None:
    now_iso = _iso_utc(datetime.now(timezone.utc))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO user (
            id, name, email, emailVerified, image, role, teamRole, banned, banExpires, createdAt, updatedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            email,
            1,
            image,
            role,
            team_role,
            int(banned),
            _iso_utc(ban_expires) if ban_expires else None,
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    conn.close()


def _insert_session(
    db_path: Path, session_id: str, token: str, user_id: str, expires_at: datetime
) -> None:
    now_iso = _iso_utc(datetime.now(timezone.utc))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO session (id, expiresAt, token, createdAt, updatedAt, ipAddress, userAgent, userId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, _iso_utc(expires_at), token, now_iso, now_iso, None, None, user_id),
    )
    conn.commit()
    conn.close()


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def test_validate_session_valid_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "better-auth.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    _create_better_auth_db(db_path)
    _insert_user(
        db_path, "u1", "Alice", "alice@example.com", "https://img.example.com/alice.png"
    )
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    _insert_session(db_path, "s1", "valid-token-abc", "u1", future)

    result = validate_session("valid-token-abc")
    assert result is not None
    assert isinstance(result, AuthUser)
    assert result.id == "u1"
    assert result.name == "Alice"
    assert result.email == "alice@example.com"
    assert result.image == "https://img.example.com/alice.png"
    assert result.role == "member"
    assert result.workspace_id == "00000000-0000-0000-0000-000000000001"
    assert result.disabled is False


def test_validate_session_prefers_team_role_and_rejects_banned_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "better-auth.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    _create_better_auth_db(db_path)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    _insert_user(
        db_path,
        "u-ban",
        "Banned User",
        "banned@example.com",
        role="admin",
        team_role="owner",
        banned=True,
        ban_expires=future,
    )
    _insert_session(db_path, "s-ban", "banned-token", "u-ban", future)

    result = validate_session("banned-token")
    assert result is None


def test_validate_session_expired_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "better-auth.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    _create_better_auth_db(db_path)
    _insert_user(db_path, "u2", "Bob", "bob@example.com")
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    _insert_session(db_path, "s2", "expired-token-xyz", "u2", past)

    result = validate_session("expired-token-xyz")
    assert result is None


def test_validate_session_missing_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "better-auth.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    _create_better_auth_db(db_path)

    result = validate_session("nonexistent-token")
    assert result is None


def test_validate_session_signed_cookie_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "better-auth.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(db_path))

    _create_better_auth_db(db_path)
    _insert_user(db_path, "u3", "Carol", "carol@example.com")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    _insert_session(db_path, "s3", "raw-token-123", "u3", future)

    result = validate_session("raw-token-123.mock-signature")
    assert result is not None
    assert result.id == "u3"


def test_normalize_session_token_strips_signature_suffix() -> None:
    assert normalize_session_token("plain-token") == "plain-token"
    assert normalize_session_token("plain-token.signature") == "plain-token"


def test_validate_session_db_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nonexistent = tmp_path / "does-not-exist.db"
    monkeypatch.setattr(settings, "better_auth_db_path", str(nonexistent))

    result = validate_session("any-token")
    assert result is None
