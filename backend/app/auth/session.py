from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from app.config import settings
from app.utils.logging import get_logger
from app.workspace import DEFAULT_WORKSPACE_ID

logger = get_logger(__name__)
_reported_schema_gaps: set[tuple[str, tuple[str, ...]]] = set()


class AuthUser(BaseModel):
    """Authenticated user read from Better Auth's SQLite DB."""

    id: str
    name: str
    email: str
    image: str | None = None
    role: str = "member"
    workspace_id: str = DEFAULT_WORKSPACE_ID
    disabled: bool = False


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _warn_schema_not_ready_once(db_path: Path, missing_tables: list[str]) -> None:
    key = (str(db_path), tuple(missing_tables))
    if key in _reported_schema_gaps:
        return
    _reported_schema_gaps.add(key)
    logger.warning(
        "auth.db_schema_not_ready",
        path=str(db_path),
        missing_tables=missing_tables,
    )


def _build_session_query(user_columns: set[str]) -> str:
    columns = [
        'u.id as id',
        'u.name as name',
        'u.email as email',
        'u.image as image',
    ]
    optional_columns = {
        "role": 'u.role as auth_role',
        "teamRole": 'u."teamRole" as team_role',
        "banned": 'u.banned as banned',
        "banExpires": 'u."banExpires" as ban_expires',
    }
    for name, fragment in optional_columns.items():
        if name in user_columns:
            columns.append(fragment)
    return f"""
SELECT {", ".join(columns)}
FROM session s
JOIN user u ON s."userId" = u.id
WHERE s.token = ? AND s."expiresAt" > ?
"""


def normalize_session_token(cookie_value: str) -> str:
    """Extract the raw Better Auth session token from a signed cookie value."""
    token, _, _signature = cookie_value.partition(".")
    return token


def validate_session(token: str) -> AuthUser | None:
    """Validate a Better Auth session token against the shared SQLite DB.

    Returns an AuthUser if the token is valid and not expired, otherwise None.
    Better Auth stores ``expiresAt`` as an ISO-8601 UTC timestamp string.
    """
    db_path = Path(settings.better_auth_db_path)
    if not db_path.is_absolute():
        db_path = Path(settings.repo_root) / db_path

    if not db_path.exists():
        logger.warning("auth.db_not_found", path=str(db_path))
        return None

    try:
        raw_token = normalize_session_token(token)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            required_tables = {"session", "user"}
            missing_tables = sorted(required_tables - _table_names(conn))
            if missing_tables:
                _warn_schema_not_ready_once(db_path, missing_tables)
                return None
            user_columns = _column_names(conn, "user")
            session_query = _build_session_query(user_columns)
            now_iso = (
                datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            row = conn.execute(session_query, (raw_token, now_iso)).fetchone()
            if row is None:
                return None
            disabled = bool(row["banned"]) if "banned" in row.keys() else False
            if disabled and "ban_expires" in row.keys() and row["ban_expires"]:
                try:
                    expires_at = datetime.fromisoformat(
                        str(row["ban_expires"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    expires_at = None
                if expires_at is not None and expires_at <= datetime.now(timezone.utc):
                    disabled = False
            if disabled:
                return None

            role = "member"
            if "team_role" in row.keys() and row["team_role"]:
                role = str(row["team_role"])
            elif "auth_role" in row.keys() and str(row["auth_role"]) == "admin":
                role = "admin"
            return AuthUser(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                image=row["image"],
                role=role,
                disabled=disabled,
            )
        finally:
            conn.close()
    except Exception:
        logger.exception("auth.session_validation_error")
        return None
