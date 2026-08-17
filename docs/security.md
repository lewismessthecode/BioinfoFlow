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
  the runtime subdirectories under `~/.bioinfoflow`

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

Uninstalling preserves `~/.bioinfoflow`, including native skills; purging explicitly removes it:

```bash
~/.bioinfoflow/install/install.sh --uninstall
~/.bioinfoflow/install/install.sh --purge
```

For an existing managed stack, neither command deletes anything until the
installer confirms that `docker compose down` succeeded through a local Unix
socket whose normalized path matches the socket recorded during installation. A
missing Docker client, unavailable daemon or Compose plugin, remote or different
local context, or stop failure leaves control files and data intact. After a
successful uninstall has removed the managed stack, a separately downloaded
installer may purge the marked Bioinfoflow home without Docker.

## Docker Socket

The Docker Compose setup mounts:

```yaml
- type: bind
  source: ${DOCKER_SOCKET_PATH:-/var/run/docker.sock}
  target: /var/run/docker.sock
  read_only: false
```

`DOCKER_SOCKET_PATH` is the host path used by the Compose bind mount;
`DOCKER_SOCKET=unix:///var/run/docker.sock` is the backend-visible URI. The
socket must be writable for Docker API operations. It gives the backend and
workflow scheduler complete authority over the host Docker daemon. Agent Bash
does not run in that backend identity: each call is delegated to a disposable
container that receives explicit project/source/skill roots read-only, its
workspace read-write, and its own request file, but never control-plane state,
another request, the Docker socket, or arbitrary host binds. Use the stack only
on trusted machines and trusted networks because a
backend compromise still reaches the daemon.

For recovery, use the same Compose file set that started the deployment for
both inspection and backend recreation:

```bash
# Source-build deployment:
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml up -d --build --force-recreate backend

# Published production images:
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml up -d --force-recreate backend

# Append the GPU override to whichever base command started the deployment:
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build --force-recreate backend
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml config
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --force-recreate backend
```

The backend must remain non-privileged, retain Docker's default seccomp and
AppArmor policies, and must not gain `SYS_ADMIN`. `AGENT_SANDBOX_IMAGE` must
resolve to the exact immutable image digest used by the running backend. The
disposable Agent container drops every capability, sets `no-new-privileges`,
uses a read-only root and bounded tmpfs, and retains Docker's default seccomp
and AppArmor policies. A confirmed `danger-full-access` call gets an ephemeral
writable image root but no additional persistent mount or Docker authority.

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
  administrator-managed OpenSSH routing when appropriate
- treat Bioinfoflow's saved jump-host mode as two SSH sessions, not OpenSSH
  `ProxyJump`: Bioinfoflow authenticates only to the saved direct jump
  connection, then the jump host's local `ssh` authenticates to the target
- keep target private keys on the jump host; the inner SSH session uses that
  host's `~/.ssh/config`, agent, keys, and OpenSSH host-key policy, including its
  local `known_hosts`, and Bioinfoflow does not introduce agent forwarding
- grant jump-host access carefully: a compromised jump host, or an account with
  authority to change its SSH config, keys, agent, or host-key records, can
  control or impersonate the inner target route within that account's authority
- remember that saved jump routes support one direct hop only and are reused by
  tests, probes, remote project terminals, and remote Harness workspaces
- remote Agent `read`, `edit`, `write`, and `bash` require a verified
  Bubblewrap runtime on the SSH host; missing, writable, or untrusted sandbox
  components fail closed
- keep the configured remote root narrow: the remote sandbox binds declared
  read/write roots, while the SSH account, ACLs, sudo rules, and scheduler policy
  remain independent authority layers
- treat command-risk path checks as lexical defense in depth: they recognize
  explicit destinations and symlinks created in the same command, but cannot
  prove the target of pre-existing symlinks or inspect archive contents before
  extraction; opaque archive extraction and unsupported indirect shell syntax
  therefore require explicit confirmation; the local or remote OS sandbox,
  SSH account, and server policy remain the enforcement boundaries
- connection authorization is scoped to the connection selected in the Agent
  Session; a command cannot substitute another connection ID
- remote authenticated `bif` requires a non-loopback
  `BIOINFOFLOW_PUBLIC_API_BASE_URL` reachable from the SSH host; the short-lived
  Agent token is passed through stdin only for a verified plain `bif` command
  and is never embedded in SSH or shell argv
- remember that remote project terminals are backend-mediated SSH PTY sessions;
  the browser still does not connect to SSH hosts directly

Remote Connections are intended for diagnostics and agent-assisted operation of
existing remote commands, plus interactive access to configured remote project
roots. They are not a general workflow dispatch backend.

## Public Origins And Hosts

Before exposing Bioinfoflow beyond localhost, set values that exactly match the browser and backend origins:

```env
BIOINFOFLOW_BIND_HOST=0.0.0.0
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER:8000/api/v1
BIOINFOFLOW_PUBLIC_API_BASE_URL=http://YOUR_SERVER:8000/api/v1
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

## Agent Harness Isolation And Authorization

The model sees only `read`, `bash`, `edit`, `write`, and `ask_user`. Product
operations go through the normal `bif` CLI and HTTP APIs instead of privileged
in-process model tools.

Local Bash requires an operating-system sandbox and fails closed. The pinned
DeepSeek local provider selects Bubblewrap or Landlock on Linux and Seatbelt on
macOS. Its contract protects filesystem integrity, not confidentiality: files
visible to the execution identity may be read except BioinfoFlow state/auth and
request capability roots, process metadata such as `/proc`, and credential
configuration paths, while writes are restricted to the canonical
workspace in confined modes. Network and process visibility are not sandbox
properties. Compose defines a narrower execution identity from the
backend image plus explicit public data roots, then adds a disposable
socket-free container around every local Bash call so Docker authority and
control-plane credentials are not ambient.

The canonical workspace must not be `/`, a user home containing credential
stores, the whole `BIOINFOFLOW_HOME`, or any directory that contains or is
contained by a protected capability path. Such a Session fails closed before a
container starts. Use a dedicated project subdirectory instead.

Remote Harness tools use the same logical root policy but establish confinement
inside the selected SSH account. Before executing a helper or Bash command, the
adapter verifies remote Bubblewrap, shell, Python, and runtime roots outside
writable project directories. Failure to find or trust them aborts the command.
The scoped authenticated `bif` path remains a separate short-lived capability;
it is not evidence of general network isolation.

Permission mode is a separate interaction policy:

- `read_only` permits reads and read-only Bash only
- `ask_dangerous` asks before destructive and critical Bash
- `full_access` reduces risk prompts but does not bypass commands explicitly
  marked for confirmation

Hard path, target, sandbox, and server-authorization violations remain blocked
in every mode. A local Bash call can request a one-shot
`require_escalated`/`danger-full-access` execution, but it always requires an
exact-call approval and remains inside the socket-free disposable container in
Compose. Questions, command confirmation, and recovery choices use the same
persisted Harness interaction channel.

Command classification is defense in depth, not complete parsing of arbitrary
shell programs. The enforceable boundaries are the local or remote OS sandbox,
the SSH account and server controls, and Bioinfoflow API authorization.

### Short-lived Agent token

Each active Run may receive a short-lived bearer token bound to its user,
workspace, Session, Run, project, and selected remote connection. The database
stores only a hash. The token expires quickly and is revoked when the Run is
cancelled or ends, or when the Session is deleted.

The token is exposed only to a command proven to be one plain `bif` invocation;
shell composition, redirection, expansion, wrappers, and `--base-url` overrides
do not receive it. Local execution injects it only into that child process.
Remote execution sends it through stdin and reconstructs the environment inside
the trusted sandbox, so it is absent from SSH argv and shell argv. Redaction
prevents it entering model context, history, logs, tool output, or artifacts.

Agent-token API requests still reload the current user and role and require the
route to opt into Agent-token access. Project and connection IDs must match the
token scope; a token cannot turn `full_access` into administrator authority.

## Environment Files

Keep `.env` private. Use `.env.example` as the shareable template.

Default config source:

1. shell environment
2. package-local override (`backend/.env` or `frontend/.env.local`)
3. repo-root `.env`
4. code defaults
