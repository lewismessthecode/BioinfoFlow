# Remote Connections

Remote Connections let Bioinfoflow store SSH connection profiles and operational
notes for the web UI, remote project terminals, and Agent Harness workspaces.

Use this feature when you want Bioinfoflow to diagnose or inspect a remote
server, open a project terminal, or bind an Agent Session to a remote project.
The browser never opens an SSH session directly. The frontend calls the
Bioinfoflow backend, and the backend performs the SSH operation. Probes and
Harness tools use bounded output and timeouts; project terminals use
backend-managed SSH PTY sessions.

## What You Can Do

- Save SSH profiles and operational notes per workspace.
- Test a connection from the Connections page.
- Run a short streamed probe command and see output in the UI.
- Open an interactive terminal for a remote project in its configured remote
  root path.
- Bind a project to a connection and let the Harness use its normal `read`,
  `bash`, `edit`, `write`, and `ask_user` tools inside that remote workspace.

Remote tool calls and results are recorded in canonical Session history. Large
command output may be stored as an Artifact.

## Requirements

The Bioinfoflow backend host must be able to reach the remote SSH server.

Agent tools additionally require `bwrap` (Bubblewrap), a trusted shell, and
Python 3 on the remote host. Bioinfoflow verifies that these runtime components
are outside writable project roots and fails closed when it cannot establish
the remote sandbox. Connection tests and interactive terminals have their own
execution paths and do not prove Harness sandbox readiness.

Remote Agent workspaces also need to call the Bioinfoflow API through `bif`.
Set `BIOINFOFLOW_PUBLIC_API_BASE_URL` to an HTTP(S) API URL reachable from the
remote host, including `/api/v1`, for example:

```env
BIOINFOFLOW_PUBLIC_API_BASE_URL=https://bioinfoflow.example/api/v1
```

Bioinfoflow rejects remote Agent sessions when this value is missing or points
to localhost. Local Agent workspaces may omit it and use the local development
default.

For Docker deployments, remember that SSH runs from inside the backend
container. Backend-specific paths and sockets must exist inside that container,
not only on the browser user's machine.

## Authentication Methods

The simple path is password or private-key login, similar to a desktop SSH
client. Bioinfoflow encrypts stored credential material with the configured
Bioinfoflow credential key and never returns passwords, private keys, or
passphrases from the API.

Advanced SSH methods are still available for deployments where an administrator
has already configured the backend container's SSH environment.

### Password

Use this when the remote server accepts SSH password login.

Enter the host, port, username, and password in the connection drawer. The
backend uses the password when the agent runs remote commands or reads remote
files. The password is write-only in the API: it can be replaced, but it cannot
be read back from Bioinfoflow.

### Private Key

Use this when the remote server accepts key-based login and you want Bioinfoflow
to manage the key material.

Paste an OpenSSH private key or upload the key file in the connection drawer.
If the key is encrypted, also enter its passphrase. Bioinfoflow stores the key
and passphrase encrypted and uses them from memory; you do not need to make a
`~/.ssh/...` path available inside the backend container.

### Via A Saved Jump Host

Use this when Bioinfoflow can reach and authenticate to a saved Remote
Connection, but the final target is reachable only from that host. Select **Via
jump host** and choose an existing direct connection in the same workspace.

This is session-level chained SSH, not OpenSSH `ProxyJump`. Bioinfoflow
authenticates only to the saved jump connection. After that outer session is
established, it runs the jump host's local `ssh` command for the target host.
The target login therefore uses the jump host's own OpenSSH environment,
including its `~/.ssh/config`, `ssh-agent`, private keys, and `known_hosts`
policy. Target private keys stay on the jump host; Bioinfoflow does not copy
them or introduce SSH agent forwarding.

The initial implementation supports exactly one direct jump connection. A
connection using jump mode cannot be selected as another connection's jump
host. The same resolved route is used for connection tests, streamed probes,
remote directory and file browsing, Harness workspaces, and remote project
terminals.

### Connection Notes

The Host Skill field stores operational notes about the server. Good examples
include:

- default working directories
- company CLI tools such as `phoenix`
- internal service URLs or ports
- safe commands for inspecting logs and outputs
- scheduler or queue limits
- directories the agent may read or write
- commands the agent should avoid

These notes are not an authorization or sandbox policy. Put required Agent
instructions in the project's `AGENTS.md` or a discoverable Skill; the Harness
loads those through its stable prompt and normal `read` tool.

## Advanced SSH Setup

Use advanced methods only when the Bioinfoflow backend environment is already
configured for SSH. In Docker, this means the backend container, not your
browser and not necessarily your host shell.

### SSH Config Alias

Use this when the backend user already has a working `~/.ssh/config` entry.

Bioinfoflow passes the alias as the SSH target. The `Host` entry owns details
such as `HostName`, `User`, `Port`, `IdentityFile`, and, if the administrator
deliberately configures it, OpenSSH `ProxyJump`. The host, user, and port fields
in Bioinfoflow are saved as readable metadata only. This advanced alias behavior
is separate from Bioinfoflow's **Via jump host** mode, which opens an outer SSH
session and runs a second SSH command on that host.

Example:

```sshconfig
Host hpc-login
  HostName login.example.org
  User bioflow
  Port 22
  IdentityFile ~/.ssh/id_ed25519
  ProxyJump bastion.example.org
```

### Key File

Use this when the backend can access a private key file path and you do not want
Bioinfoflow to store the key material.

Bioinfoflow stores the key path and runs SSH with `-i <key_path>`. The path must
be valid from the backend process or backend container, not just from the
browser user's machine. For example, `~/.ssh/id_ed25519` means the backend
user's home directory inside the backend container.

### SSH Agent

Use this when the backend user has a running `ssh-agent` with the required key loaded.

For containers, pass the agent socket into the backend container and set
`SSH_AUTH_SOCK` so the backend process can reach it.

Example Docker Compose fragment:

```yaml
services:
  backend:
    environment:
      SSH_AUTH_SOCK: /ssh-agent
    volumes:
      - ${SSH_AUTH_SOCK}:/ssh-agent
```

If you mount SSH config or key files instead, mount them read-only and make sure
their paths match what the backend container sees:

```yaml
services:
  backend:
    volumes:
      - ~/.ssh:/home/bioflow/.ssh:ro
```

## Test A Connection

Open **Connections**, select a saved connection, and choose **Test connection**.

Bioinfoflow runs a short backend SSH command:

```bash
printf bioinfoflow-ok
```

The connection status is stored on the connection. If you edit the SSH target fields later, Bioinfoflow resets the status to `unknown` so the connection can be tested again.

## Run A Probe

Choose **Run probe** to stream a short command over WebSocket.

The probe verifies that remote stdout and stderr can return to the local UI in real time. It is intended for diagnostics, not long-running interactive work.

## Open A Remote Project Terminal

When a project is bound to a Remote Connection and a `remote_root_path`,
Bioinfoflow opens the browser terminal as an interactive SSH PTY on that host.
The backend connects through the saved connection profile, requests a terminal,
changes into the project's remote root path, and streams input, output, resize,
and exit events through the existing terminal WebSocket.

Password and pasted private-key connections use Bioinfoflow's in-process SSH
client. SSH config aliases, backend key-file paths, and backend ssh-agent
connections use the backend's system `ssh` binary so they inherit the backend
host or container SSH environment.

## Use A Remote Project With The Agent Harness

Create or select a project whose storage mode is remote, with one saved
connection and one absolute remote root. The Session snapshots that project and
connection; it cannot switch to another SSH target through a tool argument.

Local and remote Sessions expose the same five tools:

| Tool | Remote behavior |
| --- | --- |
| `read` | Read a bounded text page or supported image inside allowed roots |
| `bash` | Run a command inside verified remote Bubblewrap confinement |
| `edit` | Replace exact text and return a diff |
| `write` | Create or replace a file and return a diff |
| `ask_user` | Pause for a question, confirmation, or recovery choice |

Bioinfoflow product operations use `bif --output json` through `bash`. For this
path, the remote host must reach `BIOINFOFLOW_PUBLIC_API_BASE_URL`, and a trusted
remote `bif` executable must exist outside writable project roots. The Harness
passes its short-lived scoped token through stdin only for one proven plain
`bif` command; shell composition and `--base-url` overrides do not receive it.

The permission modes are `read_only`, `ask_dangerous`, and `full_access`.
`full_access` reduces prompts but cannot expand sandbox roots, change the saved
connection, grant sudo, or bypass Bioinfoflow API authorization. Commands that
explicitly require confirmation still pause through the same `ask_user`
interaction channel.

## Current Limits

Remote Connections provide interactive project terminals, bounded command
execution, file access, and streamed probe output. They still do not dispatch
workflow runs to remote schedulers; workflow execution remains managed by the
Bioinfoflow scheduler and registered workflow engines.

## Troubleshooting

If a test fails, check the backend environment first:

- The backend host or container can resolve the SSH alias or hostname.
- Password/private-key credentials are present and were saved after the selected
  auth method was chosen.
- For password or pasted private key auth, the backend stores the encrypted
  credential and uses its built-in SSH client. No browser or host-machine
  `~/.ssh/...` path is involved.
- For Advanced SSH config aliases, `~/.ssh/config` must exist for the backend
  user or inside the backend container.
- For Advanced backend key file paths, the key path must be visible from the
  backend process.
- For Advanced backend ssh-agent auth, `SSH_AUTH_SOCK` must be set and mounted.
- Advanced backend SSH methods use system `ssh` and require the target host to
  accept `BatchMode=yes` SSH commands. Remote project terminals also require
  PTY allocation on the target host.
- Agent Harness tools require a trusted remote `bwrap`, shell, and Python 3.
- Remote `bif` commands require `BIOINFOFLOW_PUBLIC_API_BASE_URL` to be reachable
  from the SSH host and a trusted `bif` executable on that host.

For a connection using **Via jump host**, troubleshoot the two sessions in
order:

1. Test the saved jump connection itself in Bioinfoflow.
2. Log in to that jump host and run a noninteractive target test such as:

   ```bash
   ssh -o BatchMode=yes user@target 'printf bioinfoflow-ok'
   ```

The second command must succeed using the jump host's local SSH config, agent,
keys, and host-key policy. Fix target authentication or `known_hosts` on the
jump host rather than adding target credentials to Bioinfoflow.
