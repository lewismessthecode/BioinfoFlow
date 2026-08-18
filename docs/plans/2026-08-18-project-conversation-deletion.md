# Project Conversation Deletion

## Problem

Deleting a non-default project currently leaves its Agent Harness sessions
behind. Migration `0059_complete_agent_harness` changed the project foreign key
from `ON DELETE CASCADE` to `ON DELETE SET NULL`, and the sidebar later made the
orphaning explicit by moving deleted-project sessions into the default group.

That violates the product ownership invariant: a project-scoped conversation is
part of the project control plane and must not outlive the project.

## Product Boundary

- Delete the project database record and every Agent Harness session owned by
  that project.
- Reuse the safe session-deletion lifecycle so active work is quiesced, tokens
  and event streams are retired, and application-owned attachment/artifact
  files are removed.
- Preserve the project directory on disk. Managed project roots may contain the
  user's only copy of inputs and results; external and remote roots are not
  owned by BioinfoFlow. A future "delete files too" action must be a separate,
  explicit, recoverable destructive workflow.
- State this boundary in the delete confirmation: conversations are deleted,
  disk files are retained.

## Implementation

1. Centralize the existing Agent Harness session mutation lock and durable
   deletion sequence in a service reusable by both the session and project API.
2. List project-owned sessions and delete them through that lifecycle before
   deleting the project.
3. Restore `ON DELETE CASCADE` for `agent_sessions.project_id` in the ORM and an
   Alembic migration as a database-level backstop. Keep the column nullable for
   sessions that were created without a project.
4. Remove deleted-project sessions from sidebar state immediately instead of
   rewriting their `project_id` to `null`.
5. Add backend and frontend regression tests for immediate and persisted
   deletion, plus localized confirmation copy.

## Verification

- Targeted project API regression test.
- Targeted Agent Harness session deletion tests.
- Targeted sidebar integration test.
- Backend pytest and Ruff checks appropriate to the changed modules.
- Frontend lint, i18n lint, and tests.
- Alembic upgrade against a production-like SQLite database with foreign keys
  enabled.
