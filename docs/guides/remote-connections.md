# Remote Connections

Remote Connections let Bioinfoflow store SSH connection profiles and use them from the web UI and AgentCore runtime.

Use this feature when you want Bioinfoflow to diagnose or inspect a remote server, run short existing commands, or give the agent access to a selected host. The browser never opens an SSH session directly. The frontend calls the Bioinfoflow backend, and the backend runs the system `ssh` client with bounded timeouts and output limits.

## What You Can Do

- Save SSH profiles per workspace.
- Test a connection from the Connections page.
- Run a short streamed probe command and see output in the UI.
- Select a connection in the Agent composer.
- Let AgentCore use `remote.connections.list`, `remote.read_file`, `remote.list_dir`, and `remote.exec` against the selected connection.

Remote command output is recorded as Agent action output. Command-style remote outputs can also appear as artifacts in the workbench.

## Requirements

The Bioinfoflow backend host must be able to run `ssh`.

For Docker deployments, remember that SSH runs from inside the backend container. The backend container must be able to see any files or sockets referenced by the selected authentication method.

## Authentication Methods

Bioinfoflow stores connection metadata only. Do not paste passwords or private key contents into the Connections page.

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

Use this when the backend can access a private key file path.

Bioinfoflow stores the key path and runs SSH with `-i <key_path>`. The path must be valid from the backend process or backend container, not just from the browser user's machine.

### SSH Agent

Use this when the backend user has a running `ssh-agent` with the required key loaded.

For containers, pass the agent socket into the backend container and set `SSH_AUTH_SOCK` so the backend process can reach it.

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

## Use A Connection With AgentCore

Select a remote connection in the Agent composer before sending a message. Bioinfoflow stores the selected connection id in the Agent session metadata.

When a connection is selected, AgentCore receives remote context and can use these tools:

| Tool | Purpose | Risk |
| --- | --- | --- |
| `remote.connections.list` | List selected remote connections visible to the session | read |
| `remote.read_file` | Read bounded text from a remote file | read |
| `remote.list_dir` | List bounded remote directory entries | read |
| `remote.exec` | Run a short remote diagnostic command | act_high |

`remote.exec` is approval-gated as an elevated action. Prefer `remote.read_file` and `remote.list_dir` for read-only inspection.

## Current Limits

Remote Connections currently provide bounded command execution and streamed probe output. They are not a full interactive SSH terminal or PTY session. A terminal-style xterm experience can be layered on top of the same connection model in a later release.

## Troubleshooting

If a test fails, check the backend environment first:

- The backend host or container can resolve the SSH alias or hostname.
- `ssh` is installed in the backend environment.
- `~/.ssh/config` exists for the backend user when using an SSH config alias.
- Key file paths are visible from the backend process.
- `SSH_AUTH_SOCK` is set and mounted when using SSH agent auth.
- The remote server accepts non-interactive `BatchMode=yes` SSH commands.
