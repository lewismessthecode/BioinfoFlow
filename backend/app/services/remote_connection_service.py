from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remote_connection import RemoteConnection, RemoteConnectionStatus
from app.models.remote_connection import RemoteConnectionAuthMethod
from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.schemas.remote_connection import validate_remote_connection_auth_fields
from app.services.llm.credentials import decrypt_secret, encrypt_secret
from app.services.remote_execution import RemoteConnectionConfig, SshRemoteExecutor
from app.utils.exceptions import ConflictError, ValidationError


REMOTE_CONNECTION_TARGET_FIELDS = frozenset(
    {
        "host",
        "port",
        "username",
        "auth_method",
        "ssh_alias",
        "key_path",
        "encrypted_password",
        "encrypted_private_key",
        "encrypted_passphrase",
        "jump_connection_id",
    }
)


@dataclass(frozen=True)
class RemoteConnectionTestResult:
    status: str
    error: str | None = None


class RemoteConnectionTester(Protocol):
    async def test(
        self,
        connection: RemoteConnectionConfig,
    ) -> RemoteConnectionTestResult: ...


class UnavailableRemoteConnectionTester:
    async def test(
        self, connection: RemoteConnectionConfig
    ) -> RemoteConnectionTestResult:
        del connection
        return RemoteConnectionTestResult(
            status=RemoteConnectionStatus.ERROR,
            error="SSH connection testing is not configured",
        )


class SshRemoteConnectionTester:
    def __init__(self, executor: SshRemoteExecutor | None = None) -> None:
        self.executor = executor or SshRemoteExecutor()

    async def test(
        self, connection: RemoteConnectionConfig
    ) -> RemoteConnectionTestResult:
        try:
            result = await self.executor.run(
                connection,
                "printf bioinfoflow-ok",
                timeout_seconds=10,
                output_limit=2000,
            )
        except Exception as exc:  # noqa: BLE001 - test failures should persist status
            return RemoteConnectionTestResult(
                status=RemoteConnectionStatus.ERROR,
                error=_remote_test_error_message(exc),
            )
        if result.exit_code == 0 and "bioinfoflow-ok" in result.stdout:
            return RemoteConnectionTestResult(status=RemoteConnectionStatus.ONLINE)
        return RemoteConnectionTestResult(
            status=RemoteConnectionStatus.ERROR,
            error=(
                result.stderr or result.stdout or "SSH connection test failed"
            ).strip(),
        )


class RemoteConnectionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        tester: RemoteConnectionTester | None = None,
    ) -> None:
        self.repo = RemoteConnectionRepository(session)
        self.tester = tester or SshRemoteConnectionTester()

    async def list_connections(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ):
        return await self.repo.list_for_workspace(
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
        )

    async def get_connection(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> RemoteConnection | None:
        return await self.repo.get_for_workspace(
            connection_id,
            workspace_id=workspace_id,
        )

    async def create_connection(
        self,
        data: dict,
        *,
        workspace_id: str,
    ) -> RemoteConnection:
        _validate_explicit_jump_fields(data, existing=None)
        data = _credential_payload(data, existing=None)
        validate_remote_connection_auth_fields(
            auth_method=data.get("auth_method", RemoteConnectionAuthMethod.PASSWORD),
            ssh_alias=data.get("ssh_alias"),
            key_path=data.get("key_path"),
            password=data.get("encrypted_password"),
            private_key=data.get("encrypted_private_key"),
            passphrase=data.get("encrypted_passphrase"),
            jump_connection_id=data.get("jump_connection_id"),
        )
        await self._validate_jump_reference(
            data,
            workspace_id=workspace_id,
            connection=None,
        )
        try:
            return await self.repo.create(
                **data,
                workspace_id=workspace_id,
                last_status=RemoteConnectionStatus.UNKNOWN,
            )
        except IntegrityError as exc:
            await self.repo.session.rollback()
            raise ConflictError(
                "A remote connection with this name already exists in the workspace"
            ) from exc

    async def update_connection(
        self,
        connection: RemoteConnection,
        data: dict,
    ) -> RemoteConnection:
        _validate_explicit_jump_fields(data, existing=connection)
        data = _credential_payload(data, existing=connection)
        next_auth_method = data.get("auth_method", connection.auth_method)
        validate_remote_connection_auth_fields(
            auth_method=next_auth_method,
            ssh_alias=data.get("ssh_alias", connection.ssh_alias),
            key_path=data.get("key_path", connection.key_path),
            password=data.get("encrypted_password", connection.encrypted_password),
            private_key=data.get(
                "encrypted_private_key",
                connection.encrypted_private_key,
            ),
            passphrase=data.get(
                "encrypted_passphrase",
                connection.encrypted_passphrase,
            ),
            jump_connection_id=data.get(
                "jump_connection_id",
                connection.jump_connection_id,
            ),
        )
        if (
            next_auth_method == RemoteConnectionAuthMethod.JUMP
            and connection.auth_method != RemoteConnectionAuthMethod.JUMP
            and await self.repo.has_jump_dependents(
                str(connection.id),
                workspace_id=str(connection.workspace_id),
            )
        ):
            raise ValidationError(
                "A referenced jump host cannot itself use jump authentication"
            )
        await self._validate_jump_reference(
            data,
            workspace_id=str(connection.workspace_id),
            connection=connection,
        )
        target_changed = _changes_remote_target(connection, data)
        if target_changed:
            data = {
                **data,
                "last_status": RemoteConnectionStatus.UNKNOWN,
                "last_error": None,
                "last_checked_at": None,
            }
        try:
            if target_changed:
                await self.repo.invalidate_jump_dependents(
                    str(connection.id),
                    workspace_id=str(connection.workspace_id),
                )
            return await self.repo.update_all(connection, **data)
        except IntegrityError as exc:
            await self.repo.session.rollback()
            raise ConflictError(
                "A remote connection with this name already exists in the workspace"
            ) from exc

    async def delete_connection(self, connection: RemoteConnection) -> None:
        if await self.repo.has_jump_dependents(
            str(connection.id),
            workspace_id=str(connection.workspace_id),
        ):
            raise ConflictError(
                "Remote connection is used as a jump host by one or more connections"
            )
        has_projects = await ProjectRepository(
            self.repo.session
        ).has_remote_connection_projects(
            str(connection.id),
            workspace_id=str(connection.workspace_id),
        )
        if has_projects:
            raise ConflictError(
                "Remote connection is used by one or more remote projects"
            )
        await self.repo.delete(connection)

    async def _validate_jump_reference(
        self,
        data: dict,
        *,
        workspace_id: str,
        connection: RemoteConnection | None,
    ) -> None:
        auth_method = data.get(
            "auth_method",
            connection.auth_method if connection is not None else None,
        )
        if auth_method != RemoteConnectionAuthMethod.JUMP:
            return
        jump_connection_id = data.get(
            "jump_connection_id",
            connection.jump_connection_id if connection is not None else None,
        )
        if connection is not None and str(connection.id) == str(jump_connection_id):
            raise ValidationError(
                "A remote connection cannot use itself as a jump host"
            )
        jump_connection = await self.repo.get_jump_for_workspace(
            str(jump_connection_id),
            workspace_id=workspace_id,
        )
        if jump_connection is None:
            raise ValidationError("Jump connection must exist in the same workspace")
        if jump_connection.auth_method == RemoteConnectionAuthMethod.JUMP:
            raise ValidationError("Nested jump connections are not supported")

    async def test_connection(
        self,
        connection: RemoteConnection,
    ) -> tuple[RemoteConnection, datetime]:
        result = await self.tester.test(
            await self.resolve_connection_config(connection)
        )
        if result.status not in RemoteConnectionStatus.VALUES:
            raise ValidationError(
                "Remote connection tester returned an unsupported status",
                details={"status": result.status},
            )
        checked_at = datetime.now(timezone.utc)
        updated = await self.repo.record_test_result(
            connection,
            status=result.status,
            error=result.error,
            checked_at=checked_at,
        )
        return updated, updated.last_checked_at or checked_at

    async def resolve_connection_config(
        self,
        connection: RemoteConnection,
    ) -> RemoteConnectionConfig:
        jump_config = None
        if connection.auth_method == RemoteConnectionAuthMethod.JUMP:
            jump = await self.repo.get_jump_for_workspace(
                str(connection.jump_connection_id),
                workspace_id=str(connection.workspace_id),
            )
            if jump is None:
                raise ValidationError(
                    "Jump connection must exist in the same workspace"
                )
            jump_config = remote_connection_config_from_model(jump)
        return remote_connection_config_from_model(
            connection,
            jump_connection=jump_config,
        )


def remote_connection_config_from_model(
    connection: RemoteConnection,
    *,
    jump_connection: RemoteConnectionConfig | None = None,
) -> RemoteConnectionConfig:
    key_path = (
        connection.key_path
        if connection.auth_method == RemoteConnectionAuthMethod.KEY_FILE
        else None
    )
    ssh_alias = (
        connection.ssh_alias
        if connection.auth_method == RemoteConnectionAuthMethod.SSH_CONFIG
        else None
    )
    return RemoteConnectionConfig(
        id=str(connection.id),
        name=connection.name,
        host=connection.host,
        username=connection.username,
        port=connection.port,
        ssh_alias=ssh_alias,
        key_path=key_path,
        password=(
            decrypt_secret(connection.encrypted_password)
            if connection.auth_method == RemoteConnectionAuthMethod.PASSWORD
            else None
        ),
        private_key=(
            decrypt_secret(connection.encrypted_private_key)
            if connection.auth_method == RemoteConnectionAuthMethod.PRIVATE_KEY
            else None
        ),
        passphrase=(
            decrypt_secret(connection.encrypted_passphrase)
            if connection.auth_method == RemoteConnectionAuthMethod.PRIVATE_KEY
            else None
        ),
        status=connection.last_status,
        skill_summary=connection.skill_instructions,
        jump_connection=jump_connection,
    )


def _credential_payload(
    data: dict,
    *,
    existing: RemoteConnection | None,
) -> dict:
    next_data = dict(data)
    password = next_data.pop("password", None)
    private_key = next_data.pop("private_key", None)
    passphrase = next_data.pop("passphrase", None)
    auth_method = next_data.get(
        "auth_method",
        existing.auth_method
        if existing is not None
        else RemoteConnectionAuthMethod.PASSWORD,
    )

    if auth_method == RemoteConnectionAuthMethod.PASSWORD:
        if password is not None:
            next_data["encrypted_password"] = encrypt_secret(password)
        next_data["encrypted_private_key"] = None
        next_data["encrypted_passphrase"] = None
        next_data["ssh_alias"] = None
        next_data["key_path"] = None
    elif auth_method == RemoteConnectionAuthMethod.PRIVATE_KEY:
        if private_key is not None:
            next_data["encrypted_private_key"] = encrypt_secret(private_key)
        if passphrase is not None:
            next_data["encrypted_passphrase"] = (
                encrypt_secret(passphrase) if passphrase else None
            )
        next_data["encrypted_password"] = None
        next_data["ssh_alias"] = None
        next_data["key_path"] = None
    else:
        next_data["encrypted_password"] = None
        next_data["encrypted_private_key"] = None
        next_data["encrypted_passphrase"] = None
        if auth_method != RemoteConnectionAuthMethod.SSH_CONFIG:
            next_data["ssh_alias"] = None
        if auth_method != RemoteConnectionAuthMethod.KEY_FILE:
            next_data["key_path"] = None

    if auth_method == RemoteConnectionAuthMethod.JUMP:
        next_data["ssh_alias"] = None
        next_data["key_path"] = None
    else:
        next_data["jump_connection_id"] = None

    return next_data


def _validate_explicit_jump_fields(
    data: dict,
    *,
    existing: RemoteConnection | None,
) -> None:
    auth_method = data.get(
        "auth_method",
        existing.auth_method
        if existing is not None
        else RemoteConnectionAuthMethod.PASSWORD,
    )
    if auth_method != RemoteConnectionAuthMethod.JUMP:
        if data.get("jump_connection_id") is not None:
            raise ValidationError(
                f"jump_connection_id must be empty when auth_method is {auth_method}"
            )
        return
    credential_fields = (
        "password",
        "private_key",
        "passphrase",
        "ssh_alias",
        "key_path",
    )
    if any(data.get(field) is not None for field in credential_fields):
        raise ValidationError(
            "Direct credentials must be empty when auth_method is jump"
        )


def _remote_test_error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return f"SSH connection test failed: {message}"


def _changes_remote_target(connection: RemoteConnection, data: dict) -> bool:
    for field in REMOTE_CONNECTION_TARGET_FIELDS:
        if field in data and data[field] != getattr(connection, field):
            return True
    return False
