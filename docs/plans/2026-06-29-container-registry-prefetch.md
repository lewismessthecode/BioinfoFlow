# Container Registry Prefetch Implementation Plan

**Goal:** Add optional, configurable container registries for Bioinfoflow so Harbor can be a global default or selected source while existing Docker Hub, explicit image names, and tarball imports keep working.

**Architecture:** Model registries as a generic backend resource with encrypted or environment-backed credentials. Image pulls accept optional registry auth, and workflow registration may prefetch static container images using a selected or default registry without making registry configuration mandatory.

**Phases:**

- [ ] **Phase 1: Backend registry core**
  - Use `/api/v1/container-registries` with flat request fields.
  - Keep secrets encrypted/redacted and expose only hints.
  - Add `container_registries` and `projects.container_registry_id` migration.
  - Add optional `auth_config`/`registry_id` to Docker and image pull services.

- [ ] **Phase 2: Workflow image prefetch**
  - Extract static task container images from workflow schema.
  - Rewrite only unqualified images through the selected/default registry namespace.
  - Respect explicit registries such as `quay.io/...` and `localhost:5000/...`.
  - Do not fail workflow registration only because prefetch failed.

- [ ] **Phase 3: Minimal frontend integration**
  - Add a compact optional registry selector to image pull and workflow registration.
  - Preserve direct image pull and tarball import flows.
  - Keep copy localized in English and Chinese.

- [ ] **Phase 4: Documentation and validation**
  - Document Harbor as one optional registry configuration, not the only path.
  - Run targeted backend/frontend tests, then broader checks for touched areas.
  - Commit after each validated phase.

- [ ] **Phase 5: Review and PR**
  - Dispatch parallel reviewers for backend, frontend/UX, and secret handling.
  - Fix findings, run final verification, push the branch, and open a PR.
