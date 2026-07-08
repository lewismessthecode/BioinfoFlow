# Security Notes

Bioinfoflow is designed first for trusted local machines and lab servers. Treat it like infrastructure that can launch containers and access local data.

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

On first startup with local email/password auth enabled, the frontend auth layer bootstraps the owner account from:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

Change these before exposing a server.

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
- treat `remote.exec` as an elevated agent action; it runs a remote shell command
  on the selected host
- use `remote.read_file` and `remote.list_dir` for read-only inspection
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

## Environment Files

Keep `.env` private. Use `.env.example` as the shareable template.

Default config source:

1. shell environment
2. package-local override (`backend/.env` or `frontend/.env.local`)
3. repo-root `.env`
4. code defaults
