from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


TEST_USER_ID = "test-user-1"
TEST_USER_EMAIL = "test@example.com"
TEST_SESSION_TOKEN = "valid-session-token"
TEST_SESSION_COOKIE = f"{TEST_SESSION_TOKEN}.mock-signature"


def create_better_auth_db(
    db_path: Path,
    *,
    user_id: str = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    session_token: str = TEST_SESSION_TOKEN,
    expires_in_hours: int = 1,
) -> None:
    """Create a minimal Better Auth DB with one valid session."""
    now_iso = _iso_utc(datetime.now(timezone.utc))
    expires_iso = _iso_utc(
        datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
    )

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                emailVerified INTEGER NOT NULL,
                image TEXT,
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
        conn.execute(
            """
            INSERT INTO user (id, name, email, emailVerified, image, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, "Test User", email, 1, None, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO session (id, expiresAt, token, createdAt, updatedAt, ipAddress, userAgent, userId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sess-1",
                expires_iso,
                session_token,
                now_iso,
                now_iso,
                None,
                None,
                user_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
