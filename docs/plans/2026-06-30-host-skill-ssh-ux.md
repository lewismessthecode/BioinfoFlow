# Host Skill SSH UX Plan

## Goal

Make the connection drawer feel like a simple SSH client: host, port, username,
password or private key, and a Host Skill text area that tells the agent how to
use the remote server.

## Boundaries

- Keep the current Connections page layout and host list.
- Redesign only the right-side create/edit drawer.
- Keep remote tools generic: SSH command execution plus file/directory access.
- Do not add Bioinfoflow run directories, workflow lifecycle abstractions, or
  workflow-specific tools.
- Move backend-specific SSH config, backend key paths, and backend ssh-agent
  behavior into advanced options and docs.

## Implementation Phases

1. Backend auth model
   - Add `password` and `private_key` auth methods.
   - Store password/private key material encrypted and redact it from reads.
   - Keep existing `agent`, `key_file`, and `ssh_config` methods for advanced
     setups.
   - Support password/private key execution with the smallest reliable SSH
     transport change.

2. Drawer UX and copy
   - Rename Agent instructions to `Host Skill`.
   - Make password login the default user-facing auth method.
   - Show private key paste/upload fields instead of backend path by default.
   - Move backend ssh-agent, backend key path, and SSH config Host into an
     advanced section.
   - Reduce nested card borders and heavy shadows in the drawer.

3. Docs and verification
   - Document simple password/private-key setup.
   - Document advanced backend SSH behavior, including why `~/.ssh/...` means
     the backend container path.
   - Run focused backend and frontend tests, i18n lint, and visual review.

## Validation

- Backend: focused remote connection tests and ruff.
- Frontend: connection page tests, lint, i18n lint.
- Visual: run dev services with `AUTH_MODE=dev` if needed and inspect the
  drawer at desktop/mobile widths.
