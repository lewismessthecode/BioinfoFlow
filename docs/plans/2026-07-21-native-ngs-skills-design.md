# Native NGS Skills Design

## Goal

Ship the reviewed OpenAI NGS analysis skills as Bioinfoflow-native skills in
the public curl installer. A fresh install must be ready to discover and use
the skills from `~/.bioinfoflow/skills`, while later Bioinfoflow upgrades must
never overwrite that directory.

BGI/Phoenix skills are explicitly outside this design. They remain private and
user-installed.

## Home Layout

The localhost installer uses one product home, matching tools such as Codex and
Claude Code:

```text
~/.bioinfoflow/
├── install/
├── skills/
├── state/
├── projects/
└── sources/
```

`BIOINFOFLOW_HOME` resolves to `~/.bioinfoflow`. The existing default
`BIOINFOFLOW_SKILLS_ROOT=<BIOINFOFLOW_HOME>/skills` therefore needs no special
override.

The backend and frontend must not receive the installer control directory.
Compose mounts the runtime subdirectories (`skills`, `state`, `projects`, and
`sources`) individually at identity paths instead of mounting the complete
home.

## Native Skill Layout

Every discoverable skill remains a direct child of the skills root:

```text
~/.bioinfoflow/skills/<skill-name>/SKILL.md
```

The former plugin-wide runtime payload moves under `ngs-runtime-env`, which
owns shared scripts, workflows, registries, and runtime assets:

```text
ngs-runtime-env/
├── SKILL.md
├── scripts/
├── workflows/
├── references/
├── assets/
└── tests/
```

Other NGS skills remain independent directories. Their command examples use
`$BIOINFOFLOW_SKILLS_ROOT/ngs-runtime-env/scripts/...` and explicitly state
that the bundled helper path is local to the Bioinfoflow host. Remote SSH
targets continue to use connection-specific `skill_instructions`; Bioinfoflow
does not synchronize its skills directory to remote machines.

The skill context identifies the absolute skill directory so relative
`references/`, `scripts/`, `assets/`, and `templates/` paths are unambiguous.

## Release And First-Install Flow

The release workflow builds `bioinfoflow-skills.tar.gz` from the repository's
reviewed `bundled-skills/` tree and includes it in `SHA256SUMS` with the
installer and Compose file.

On a first install, the installer:

1. Downloads all version-matched release assets.
2. Verifies the complete checksum manifest.
3. Extracts the skills archive into a temporary directory.
4. Validates that every top-level skill directory has `SKILL.md` and that the
   archive cannot escape the destination.
5. Atomically moves the prepared skills directory into
   `~/.bioinfoflow/skills` before Compose starts so it can be used as a bind
   mount source.
6. Removes that newly seeded directory if a fresh installation later fails to
   start or become healthy.

An install is considered already seeded when `~/.bioinfoflow/skills` exists.
Updates and repair installs leave any existing skills directory byte-for-byte
untouched. A first-install name collision is therefore impossible unless the
user pre-created the directory; in that case the installer preserves it and
reports that bundled skills were not seeded.

## Lifecycle Semantics

- `--update` upgrades containers and installer control files only.
- `--uninstall` removes `install/` and preserves skills and application data.
- `--purge` removes the marked Bioinfoflow home, including user-modified skills.
- Rollback after a failed first install must not leave a partially seeded
  skills directory.

## Security And Integrity

- Release checksums cover the skills archive.
- Archive entries with absolute paths or `..` traversal are rejected.
- The backend cannot access `~/.bioinfoflow/install` through Compose mounts.
- The public bundle contains no BGI/Phoenix internal skills.
- Upstream attribution and source version are retained with the bundled NGS
  content.

## Verification

- Backend tests cover discovery and resource-directory context.
- Installer tests cover the new home, first-install seeding, update
  preservation, archive failure rollback, uninstall preservation, and purge.
- Release automation tests cover archive creation, checksums, smoke assets, and
  GitHub upload.
- The copied NGS script tests run from the native `ngs-runtime-env` location.
- Shell syntax, shellcheck, Compose rendering, backend tests, Ruff, and Markdown
  diff checks run before completion.
