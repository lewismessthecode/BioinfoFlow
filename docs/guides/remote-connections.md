# Remote Connections

Remote Connections let Bioinfoflow store SSH connection profiles and Host Skills
for use from the web UI and AgentCore runtime.

Use this feature when you want Bioinfoflow to diagnose or inspect a remote
server, open a project terminal, run existing commands, inspect files, or give
the agent access to a selected host. AgentCore has no dedicated remote file-write
tool; `remote.exec` commands can still modify the remote host when policy allows
them. The browser never opens an SSH session directly. The frontend calls the
Bioinfoflow backend, and the backend performs the SSH operation. Command-style
probes and AgentCore tools stay bounded by timeouts and output limits; project
terminals use backend-managed SSH PTY sessions.

## What You Can Do

- Save SSH profiles and Host Skill instructions per workspace.
- Test a connection from the Connections page.
- Run a short streamed probe command and see output in the UI.
- Open an interactive terminal for a remote project in its configured remote
  root path.
- Select a connection in the Agent composer.
- Let AgentCore use `remote.connections.list`, `remote.read_file`, `remote.list_dir`, and `remote.exec` against the selected connection.

Remote command output is recorded as Agent action output. Command-style remote outputs can also appear as artifacts in the workbench.

## Requirements

The Bioinfoflow backend host must be able to reach the remote SSH server.

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

### Host Skill

The Host Skill field tells the agent how to use this server after connecting.
Keep it operational and specific. Good examples include:

- default working directories
- company CLI tools such as `phoenix`
- internal service URLs or ports
- safe commands for inspecting logs and outputs
- scheduler or queue limits
- directories the agent may read or write
- commands the agent should avoid

Host Skill instructions are not a workflow abstraction. Bioinfoflow still gives
the agent generic SSH command and file tools; the instructions teach the agent
how to use the remote environment already provided by your team.

## Advanced SSH Setup

Use advanced methods only when the Bioinfoflow backend environment is already
configured for SSH. In Docker, this means the backend container, not your
browser and not necessarily your host shell.

### SSH Config Alias

Use this when the backend user already has a working `~/.ssh/config` entry.

Bioinfoflow passes the alias as the SSH target. The `Host` entry owns details such as `HostName`, `User`, `Port`, `IdentityFile`, and `ProxyJump`. The host, user, and port fields in Bioinfoflow are saved as readable metadata only.

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

## Use A Connection With AgentCore

Select a remote connection in the Agent composer before sending a message. Bioinfoflow stores the selected connection id in the Agent session metadata.

When a connection is selected, AgentCore receives remote context and can use these tools:

| Tool | Purpose | Risk |
| --- | --- | --- |
| `remote.connections.list` | List selected remote connections visible to the session | read |
| `remote.read_file` | Read bounded text from a remote file | read |
| `remote.list_dir` | List bounded remote directory entries | read |
| `remote.exec` | Run a short remote diagnostic command | assessed per command and SSH target |

Prefer `remote.read_file` and `remote.list_dir` for bounded read-only inspection.
`remote.exec` shares the local command-risk vocabulary but is adjusted for the
selected SSH identity and remote boundary. A safe read whose path can be bounded
may remain low risk. Writes, network access, destructive commands, protected
resources, variable or home-relative paths, outside-root paths, and uncertain
option or symlink behavior are escalated when safety cannot be proven.

The selected connection is part of the authorization context. A tool call may
not switch to another connection id. The configured remote root is used as a
working directory and a risk-analysis root; it is not a chroot, container, or
OS sandbox. A command has the privileges of the configured remote user plus any
sudo, ACL, scheduler, and server policy available to that account.

Changing the Agent permission mode affects the next authorization evaluation,
including during an active turn. With waiting tool approvals, the UI asks
whether to update future operations only or also approve eligible waiting tools.
User questions and plan approval are never bulk-approved.

**Full access** skips ordinary Bioinfoflow risk prompts for this selected host.
It does not grant additional SSH privileges. Catastrophic commands remain
blocked, and writes to protected credentials, SSH/sudo configuration, shell
startup files, or permission-policy resources still require explicit approval.

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
