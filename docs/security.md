# Security Notes

Bioinfoflow is designed first for trusted local machines and lab servers. Treat it like infrastructure that can launch containers and access local data.

## Localhost Installer Trust Boundary

The release installer creates a deliberately low-friction, single-machine
environment:

- the frontend and backend publish only on `127.0.0.1`
- both services use `AUTH_MODE=dev`, so there is no login or user isolation
- the backend mounts the effective local Unix Docker socket
- control files live in `~/.bioinfoflow/install`
- persistent state, credentials, projects, and run data live in
  `~/.bioinfoflow/data`

This is safe only when the host account and local machine are trusted. Any local
process or user that can reach the bound ports can use Bioinfoflow without
authenticating, and Docker-socket access gives the backend container authority
over the host Docker daemon. Do not expose this stack with a reverse proxy, SSH
port forwarding, a public port bind, or a remote Docker context.

Provider API keys are not accepted or stored by the installer. Connect a model
after the app opens; Bioinfoflow stores saved provider credentials through its
normal credential-encryption system under the persistent data root.

For shared or remote use, build from source and configure `personal` or `team`
auth, explicit secrets, trusted hosts, matching origins, and TLS as described
below. The localhost installer is not a shortcut for production deployment.

Uninstalling preserves `~/.bioinfoflow/data`; purging explicitly removes it:

```bash
~/.bioinfoflow/install/install.sh --uninstall
~/.bioinfoflow/install/install.sh --purge
```

## Docker Socket

The Docker Compose setup mounts:

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

That gives the backend container access to the host Docker daemon. Use it only on trusted machines and trusted networks.

## Authentication

`AUTH_MODE` supports:

- `personal`: local single-owner style setup; this is the default in `.env.example`
- `team`: multi-user mode with team roles
- `dev`: auth disabled for development and tests

When both bootstrap variables remain configured, frontend startup ensures that
the email belongs to an active owner and updates its password from:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

Change these before exposing a server. After verifying the owner account on a
long-lived shared deployment, remove the bootstrap password unless automatic
owner recovery is intentional.

## Stored Credential Encryption

AI provider keys, container-registry credentials, and stored Remote Connection
passwords or private keys use the same credential-encryption system. Team mode
requires a stable `BIOINFOFLOW_CREDENTIAL_KEY`. Personal mode generates
`BIOINFOFLOW_HOME/state/credentials/fernet.key`; back that file up with the
databases or restored credentials cannot be decrypted.

## Better Auth Secret

For local `bun run dev` development, an empty `BETTER_AUTH_SECRET` is allowed
and the frontend derives a local instance secret.

For localhost Docker, an empty `BETTER_AUTH_SECRET` is also allowed. The
frontend creates a persistent local secret under `BIOINFOFLOW_HOME/state/auth`.

For any shared or remote server, set:

```env
BETTER_AUTH_SECRET=<long-random-secret>
```

The production frontend auth path throws when `BETTER_AUTH_SECRET` is missing
and `BETTER_AUTH_URL` points at a non-local host.

## Remote Connections

Remote Connections execute from the Bioinfoflow backend host or backend
container, not from the browser.

Security expectations:

- store SSH passwords and pasted private keys only through the Remote
  Connections credential fields; Bioinfoflow encrypts them and redacts them from
  API reads
- make key files and `SSH_AUTH_SOCK` available only to the backend environment
  that needs them when using advanced backend SSH methods
- use SSH config aliases for `HostName`, `User`, `Port`, `IdentityFile`, and
  `ProxyJump` when possible
- treat `remote.exec` as a remote shell with the selected SSH account's actual
  authority; Bioinfoflow assesses each command dynamically, but does not add an
  OS sandbox to an arbitrary SSH host
- use `remote.read_file` and `remote.list_dir` for read-only inspection
- treat the configured remote root as a navigation default and policy signal,
  not confinement; absolute, variable, home-relative, outside-root, or
  symlink-sensitive paths may require approval when safety cannot be established
- treat command-risk path checks as lexical defense in depth: they recognize
  explicit destinations and symlinks created in the same command, but cannot
  prove the target of pre-existing symlinks or inspect archive contents before
  extraction; opaque archive extraction and unsupported indirect shell syntax
  therefore require explicit approval, while the local OS sandbox or remote
  Unix account and server policy remains the enforcement boundary
- connection authorization is scoped to the connection selected in the Agent
  session; a command cannot substitute another connection id
- remember that remote project terminals are backend-mediated SSH PTY sessions;
  the browser still does not connect to SSH hosts directly

Remote Connections are intended for diagnostics and agent-assisted operation of
existing remote commands, plus interactive access to configured remote project
roots. They are not a general workflow dispatch backend.

## Public Origins And Hosts

Before exposing Bioinfoflow beyond localhost, set values that exactly match the browser and backend origins:

```env
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER:3000
CORS_ORIGINS=["http://YOUR_SERVER:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER"]
```

`NEXT_PUBLIC_*` values are baked into the frontend build. Rebuild after changing them:

```bash
docker compose up -d --build
```

For access outside a trusted localhost environment, terminate TLS at a reverse
proxy and use matching `https://` origins. Do not expose the frontend and backend
ports directly to untrusted networks.

## Agent Shell Isolation

The OS-level bash sandbox for AgentCore is disabled by default. When enabled it
is fail-closed by default, with network access and unsandboxed opt-out disabled.
Docker deployments may require host user-namespace and bubblewrap support.

The sandbox and approval policy are separate controls:

- the sandbox limits what a local process can reach when an adapter is active
- permission modes decide when Bioinfoflow asks before an action
- SSH commands are constrained by the remote Unix account, sudo/ACL policy,
  scheduler policy, and server configuration, not by the local sandbox

"Full access" (`bypass`) skips ordinary risk prompts for the selected target.
It does not disable an active local sandbox or bypass remote account authority.
High-confidence matches for catastrophic operations, including recognized root
filesystem destruction, unsafe block-device writes or formats, direct host
shutdown/reboot, and fork-bomb forms, are hard denied even in Full access.
Dynamic or indirect command forms that cannot be proved safe require explicit
approval, as do sandbox opt-out and writes to protected credentials, SSH
configuration, sudoers, shell startup files, and permission-policy resources.

Command classification is a policy and review aid, not complete shell
confinement: obfuscated programs and runtime-generated arguments cannot all be
understood statically. The enforceable boundary is an active local OS sandbox;
for SSH execution it is the remote Unix account plus sudo, ACL, scheduler, and
server policy. Keep those controls enabled even when approval prompts are
relaxed.

## Agent Permission And Approval Integrity

AgentCore treats permission state as versioned authorization data. Each change
to permission mode, automation mode, role/toolset, or execution target advances
`permission_policy_version`. Before exposing or authorizing a tool, the runtime
forces a fresh database read and stores a bounded permission and target snapshot
on the resulting action. A committed change therefore applies to the next
authorization evaluation in an active turn; already running or terminal actions
are not rewritten.

Permission updates default to `future_only`. The optional
`approve_pending_tools` strategy approves eligible waiting tool actions in the
same transaction as the policy update, but excludes `ask_user` and plan approval.
The response reports affected, excluded, and already-resolved counts.

Assistant tool calls are persisted in batches. The model cannot continue until
every call in the batch has a completed, failed, rejected, or cancelled result.
Approval decisions, execution claims, and batch continuation use conditional
database transitions so duplicate requests, queue deliveries, workers, and
restarts do not intentionally execute or continue twice. A process lost during
a running side effect is failed for manual reconciliation rather than replayed.

## Environment Files

Keep `.env` private. Use `.env.example` as the shareable template.

Default config source:

1. shell environment
2. package-local override (`backend/.env` or `frontend/.env.local`)
3. repo-root `.env`
4. code defaults
