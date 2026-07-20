# Pixel Default Avatars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Bioinfoflow user a stable, designed pixel avatar and add account controls for choosing a built-in avatar, uploading a cropped custom image, and restoring the default.

**Architecture:** A pure avatar catalog and resolver produces deterministic built-in identities from viewer IDs. A shared `UserAvatar` component renders reserved built-in avatar references or normal image URLs consistently in the sidebar and settings. Authenticated changes go through a Next.js profile-avatar route that updates Better Auth and stores normalized WebP files under `BIOINFOFLOW_HOME`; development mode uses a small browser-local preference store.

**Tech Stack:** Next.js 16, React 19, TypeScript, Better Auth, Radix Avatar/Dialog, `react-avatar-editor`, Sharp, Vitest, Testing Library, next-intl.

---

## File Structure

- Create `frontend/lib/avatar/pixel-personas.ts`: stable catalog keys, 12-by-12 pixel definitions, hashing, candidate paging, and reserved image-reference helpers.
- Create `frontend/lib/avatar/avatar-preference.ts`: development-mode local preference storage and cross-component change events.
- Create `frontend/components/bioinfoflow/user-avatar.tsx`: shared resolver and renderer for uploaded, selected, and deterministic avatars.
- Create `frontend/components/bioinfoflow/settings/avatar-upload-dialog.tsx`: square crop and zoom interaction that emits a normalized WebP blob.
- Create `frontend/components/bioinfoflow/settings/avatar-settings-panel.tsx`: current preview, six candidates, paging, upload, reset, and save feedback.
- Create `frontend/lib/avatar/avatar-storage.ts`: server-only safe paths, normalized upload validation, atomic writes, reads, and cleanup.
- Create `frontend/app/api/profile/avatar/route.ts`: authenticated select, upload, and reset mutations.
- Create `frontend/app/api/profile/avatar/file/route.ts`: authenticated delivery of the current user’s stored avatar.
- Modify `frontend/components/bioinfoflow/user-menu.tsx`: replace direct Radix avatar logic with `UserAvatar`.
- Modify `frontend/components/bioinfoflow/settings/settings-page-client.tsx`: include `viewer.image` and render the avatar panel in Account settings.
- Modify `frontend/app/(app)/settings/page.tsx`: pass `viewer.image` to the client page.
- Modify `frontend/messages/en.json` and `frontend/messages/zh-CN.json`: add avatar labels, help text, status, and errors.
- Modify `frontend/package.json` and `frontend/bun.lock`: declare `react-avatar-editor` and `sharp` directly.
- Create `frontend/tests/unit/lib/pixel-personas.test.ts`: deterministic mapping and reference parsing.
- Create `frontend/tests/unit/components/user-avatar.test.tsx`: render and fallback behavior.
- Create `frontend/tests/unit/components/avatar-settings-panel.test.tsx`: candidate, save, upload, reset, and development-local behavior.
- Create `frontend/tests/unit/avatar-storage.test.ts`: safe server storage behavior.
- Create `frontend/tests/unit/profile-avatar-route.test.ts`: route authorization, validation, update ordering, and reset behavior.
- Modify `frontend/tests/unit/components/user-menu.test.tsx` and `frontend/tests/unit/components/settings-page.test.tsx`: integration coverage for the new shared component and Account section.

### Task 1: Deterministic Pixel Persona Catalog

**Files:**
- Create: `frontend/tests/unit/lib/pixel-personas.test.ts`
- Create: `frontend/lib/avatar/pixel-personas.ts`

- [ ] **Step 1: Write failing catalog tests**

Cover these public contracts:

```ts
expect(PIXEL_PERSONAS).toHaveLength(20)
expect(resolveDefaultPixelPersona("viewer-1")).toBe(
  resolveDefaultPixelPersona("viewer-1"),
)
expect(resolveDefaultPixelPersona("viewer-1").key).toMatch(/^pixel-persona-/)
expect(parsePixelPersonaReference(toPixelPersonaReference("pixel-persona-03")))
  .toBe("pixel-persona-03")
expect(parsePixelPersonaReference("https://example.com/avatar.webp")).toBeNull()
expect(getPixelPersonaCandidates("viewer-1", 0, 6)).toHaveLength(6)
expect(getPixelPersonaCandidates("viewer-1", 1, 6)).not.toEqual(
  getPixelPersonaCandidates("viewer-1", 0, 6),
)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk bun run test tests/unit/lib/pixel-personas.test.ts` from `frontend/`.

Expected: FAIL because `@/lib/avatar/pixel-personas` does not exist.

- [ ] **Step 3: Implement the catalog and resolver**

Define:

```ts
export type PixelPersona = {
  key: `pixel-persona-${string}`
  background: string
  palette: Record<string, string>
  pixels: readonly string[]
}

export const PIXEL_PERSONA_REFERENCE_PREFIX = "bioinfoflow-avatar:"
export const PIXEL_PERSONAS: readonly PixelPersona[]
export function resolveDefaultPixelPersona(viewerId: string): PixelPersona
export function getPixelPersonaCandidates(
  viewerId: string,
  page: number,
  count?: number,
): PixelPersona[]
export function toPixelPersonaReference(key: PixelPersona["key"]): string
export function parsePixelPersonaReference(value?: string | null): PixelPersona["key"] | null
export function findPixelPersona(key: string): PixelPersona | null
```

Use a stable string hash and modular indexing. Do not use `Math.random()`.
Populate keys `pixel-persona-01` through `pixel-persona-20`. Keep sixteen
portraits accessory-free and give four portraits exactly one restrained detail:
square glasses, round glasses, a lab cap, or a single-ear headset. Reuse the
approved navy/teal, aubergine/lilac, rust/ochre, blue/stone, and moss/cream color
families so every catalog entry is manually reviewable.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `rtk bun run test tests/unit/lib/pixel-personas.test.ts`.

Expected: PASS.

### Task 2: Shared Avatar Rendering And Development Preference

**Files:**
- Create: `frontend/tests/unit/components/user-avatar.test.tsx`
- Create: `frontend/lib/avatar/avatar-preference.ts`
- Create: `frontend/components/bioinfoflow/user-avatar.tsx`
- Modify: `frontend/components/bioinfoflow/user-menu.tsx`
- Modify: `frontend/tests/unit/components/user-menu.test.tsx`

- [ ] **Step 1: Write failing renderer tests**

Verify that `UserAvatar`:

```tsx
render(<UserAvatar viewerId="viewer-1" name="Alice" image="bioinfoflow-avatar:pixel-persona-03" />)
expect(screen.getByTestId("pixel-persona-03")).toBeInTheDocument()

render(<UserAvatar viewerId="viewer-1" name="Alice" image="/api/profile/avatar/file?v=1" />)
expect(screen.getByRole("img")).toHaveAttribute("src", "/api/profile/avatar/file?v=1")

render(<UserAvatar viewerId="viewer-1" name="Alice" />)
expect(screen.getByTestId(resolveDefaultPixelPersona("viewer-1").key)).toBeInTheDocument()
```

Also verify that the development preference store reads, writes, clears, and
dispatches one browser event so the sidebar updates without a reload.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `rtk bun run test tests/unit/components/user-avatar.test.tsx tests/unit/components/user-menu.test.tsx`.

Expected: FAIL because `UserAvatar` and the new preference store do not exist.

- [ ] **Step 3: Implement the shared component and store**

`UserAvatar` accepts the viewer ID, name, explicit image, auth mode, size class,
and decorative/accessible alt behavior. It renders inline crisp SVG for built-in
personas and Radix `AvatarImage` for uploaded or OAuth images. A failed external
image reveals the deterministic persona fallback; initials remain the last
fallback only when no viewer ID is available.

Use `useSyncExternalStore` in `avatar-preference.ts` with:

```ts
export const DEV_AVATAR_STORAGE_KEY = "bioinfoflow.avatar.dev"
export function readDevAvatarPreference(): string | null
export function writeDevAvatarPreference(value: string): void
export function clearDevAvatarPreference(): void
export function subscribeDevAvatarPreference(listener: () => void): () => void
```

Replace the direct avatar markup in `UserMenu` with `UserAvatar`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `rtk bun run test tests/unit/components/user-avatar.test.tsx tests/unit/components/user-menu.test.tsx`.

Expected: PASS.

### Task 3: Avatar Settings Panel And Crop Dialog

**Files:**
- Create: `frontend/tests/unit/components/avatar-settings-panel.test.tsx`
- Create: `frontend/components/bioinfoflow/settings/avatar-upload-dialog.tsx`
- Create: `frontend/components/bioinfoflow/settings/avatar-settings-panel.tsx`
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Modify: `frontend/app/(app)/settings/page.tsx`
- Modify: `frontend/tests/unit/components/settings-page.test.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/bun.lock`

- [ ] **Step 1: Declare crop dependencies**

Run: `rtk bun add react-avatar-editor sharp` from `frontend/`.

Expected: both packages appear in direct dependencies and the lockfile remains
consistent.

- [ ] **Step 2: Write failing settings tests**

Test authenticated behavior with a mocked `fetch`:

```ts
expect(screen.getAllByRole("radio", { name: /Pixel avatar/ })).toHaveLength(6)
fireEvent.click(screen.getByRole("button", { name: "Show another set" }))
expect(screen.getAllByRole("radio", { name: /Pixel avatar/ })[0]).not.toHaveAttribute(
  "data-avatar-key",
  firstKey,
)
fireEvent.click(screen.getByRole("radio", { name: "Pixel avatar 3" }))
await waitFor(() => expect(fetch).toHaveBeenCalledWith(
  "/api/profile/avatar",
  expect.objectContaining({ method: "PATCH" }),
))
```

Test development mode writes the selected built-in reference and cropped data
URL to browser-local storage. Test upload type rejection, reset, disabled saving
controls, and success/error toasts.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `rtk bun run test tests/unit/components/avatar-settings-panel.test.tsx tests/unit/components/settings-page.test.tsx`.

Expected: FAIL because the panel and upload dialog do not exist.

- [ ] **Step 4: Implement the crop dialog**

Use `react-avatar-editor` in a compact dialog. Accept PNG, JPEG, and WebP up to
5 MiB, expose zoom from 1 to 2.5, and on confirmation call
`getImageScaledToCanvas().toBlob(..., "image/webp", 0.88)` to produce a
256-by-256 WebP. Revoke temporary object URLs on close.

- [ ] **Step 5: Implement the settings panel**

Render a restrained account card with a 72-pixel preview, six candidate avatars,
`Show another set`, `Upload image`, and conditional `Restore default` actions.
Use radio semantics, visible focus rings, and `aria-live` save feedback. For
authenticated viewers call the profile route and refresh the router after a
successful save. For development mode use the local preference store.

- [ ] **Step 6: Integrate the panel and viewer image**

Add `image?: string | null` to `SettingsPageClientProps`, pass it from the server
settings page, and place `AvatarSettingsPanel` before the email/role/mode group.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run: `rtk bun run test tests/unit/components/avatar-settings-panel.test.tsx tests/unit/components/settings-page.test.tsx`.

Expected: PASS.

### Task 4: Authenticated Avatar Storage And Profile Route

**Files:**
- Create: `frontend/tests/unit/avatar-storage.test.ts`
- Create: `frontend/tests/unit/profile-avatar-route.test.ts`
- Create: `frontend/lib/avatar/avatar-storage.ts`
- Create: `frontend/app/api/profile/avatar/route.ts`
- Create: `frontend/app/api/profile/avatar/file/route.ts`
- Modify: `frontend/lib/auth.ts`

- [ ] **Step 1: Write failing storage tests**

Verify:

```ts
expect(resolveAvatarStorageDir()).toBe(
  path.join(path.dirname(resolveBetterAuthDbPath()), "avatars"),
)
expect(avatarUserDigest("../unsafe")).toMatch(/^[a-f0-9]{32}$/)
await expect(validateAvatarUpload(nonWebpBlob)).rejects.toThrow("WebP")
```

Use a temporary `BIOINFOFLOW_HOME` for atomic write/read/cleanup tests.

- [ ] **Step 2: Run storage tests and verify RED**

Run: `rtk bun run test tests/unit/avatar-storage.test.ts`.

Expected: FAIL because `avatar-storage.ts` does not exist.

- [ ] **Step 3: Implement storage helpers**

Export `resolveBioinfoflowHome` from `auth.ts` and implement server-only helpers
that:

- derive a 32-character SHA-256 user digest;
- accept only WebP payloads up to 512 KiB;
- use Sharp metadata to require a 256-by-256 image;
- write `${digest}-${version}.webp` through a temporary file and atomic rename;
- read only a validated numeric version for the authenticated user;
- delete superseded versions after profile update success.

- [ ] **Step 4: Run storage tests and verify GREEN**

Run: `rtk bun run test tests/unit/avatar-storage.test.ts`.

Expected: PASS.

- [ ] **Step 5: Write failing route tests**

Cover unauthenticated 401 responses, invalid built-in keys, successful built-in
selection, invalid media, successful upload, update failure cleanup, reset, and
authenticated file delivery. Assert the internal adapter is called only with
the current session user ID.

- [ ] **Step 6: Run route tests and verify RED**

Run: `rtk bun run test tests/unit/profile-avatar-route.test.ts`.

Expected: FAIL because the profile routes do not exist.

- [ ] **Step 7: Implement profile routes**

`PATCH /api/profile/avatar` accepts `{ avatarKey }`, validates the catalog key,
and stores `toPixelPersonaReference(avatarKey)`. `POST` accepts a `file` form
field, persists it, updates `user.image` to
`/api/profile/avatar/file?v=<version>`, then removes older versions. `DELETE`
sets `user.image` to null before cleaning stored files. `GET .../file?v=` derives
the path exclusively from the session user and validated version.

- [ ] **Step 8: Run route tests and verify GREEN**

Run: `rtk bun run test tests/unit/profile-avatar-route.test.ts`.

Expected: PASS.

### Task 5: Localization And Interaction Integration

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx`

- [ ] **Step 1: Write the failing integration expectation**

Extend the settings flow fixture with avatar translations and assert the Account
section renders the preview, six candidates, and upload/reset controls with the
correct access state.

- [ ] **Step 2: Run the integration test and verify RED**

Run: `rtk bun run test tests/integration/pages/settings-page-flow.test.tsx`.

Expected: FAIL because translations and the panel are not integrated.

- [ ] **Step 3: Add English and Chinese copy**

Add keys under `settings.account.avatar` for title, description, candidate
labels, paging, upload, crop, zoom, confirm, cancel, reset, saving, success,
unsupported type, oversized file, and generic failure.

- [ ] **Step 4: Run integration and i18n checks and verify GREEN**

Run:

```bash
rtk bun run test tests/integration/pages/settings-page-flow.test.tsx
rtk bun run lint:i18n
```

Expected: both exit 0.

### Task 6: Visual Verification And Full Frontend Checks

**Files:**
- Modify only if browser verification exposes a covered defect.

- [ ] **Step 1: Run focused avatar tests together**

Run:

```bash
rtk bun run test \
  tests/unit/lib/pixel-personas.test.ts \
  tests/unit/components/user-avatar.test.tsx \
  tests/unit/components/user-menu.test.tsx \
  tests/unit/components/avatar-settings-panel.test.tsx \
  tests/unit/avatar-storage.test.ts \
  tests/unit/profile-avatar-route.test.ts \
  tests/unit/components/settings-page.test.tsx \
  tests/integration/pages/settings-page-flow.test.tsx
```

Expected: all selected tests pass with zero unhandled errors.

- [ ] **Step 2: Run repository-required frontend checks**

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
rtk bun run build
```

Expected: all commands exit 0.

- [ ] **Step 3: Perform browser visual verification**

Set `AUTH_MODE=dev` in this worktree’s repo-root `.env`, restart frontend and
backend services, open `/settings?section=account`, and verify:

- 32-pixel sidebar and 72-pixel settings previews remain crisp;
- six avatars are visually distinct in light and dark modes;
- selection, another set, upload crop, and reset work;
- responsive layout does not overflow at narrow desktop and mobile widths;
- focus, selected, disabled, and error states remain visible.

Restore machine-local environment changes that should not be committed.

- [ ] **Step 4: Inspect final diff and commit implementation**

Run:

```bash
rtk git diff --check
rtk git status --short
rtk git diff --stat
```

Stage only the feature files, then commit with:

```bash
rtk git commit -m "feat: add pixel default avatars"
```

### Task 7: Sync, Push, And Open Pull Request

- [ ] **Step 1: Confirm GitHub access**

Run:

```bash
rtk gh --version
rtk gh auth status
```

Expected: GitHub CLI is installed and authenticated.

- [ ] **Step 2: Sync the remote default branch**

Run:

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: rebase succeeds. If it changes the tested tree, rerun the focused tests,
lint, and build before pushing.

- [ ] **Step 3: Push the branch**

Run: `rtk git push -u origin codex/pixel-default-avatars`.

Expected: the remote tracking branch is created or updated.

- [ ] **Step 4: Create the pull request**

Create a ready-for-review PR because the user explicitly requested a completed,
tested implementation. Use title:

```text
feat: add pixel default avatars
```

The body summarizes the deterministic curated avatar system, account
customization and upload storage, localization, and exact verification commands.

---

## Plan Self-Review

- Every design requirement maps to Tasks 1 through 5.
- Authenticated and development-mode persistence are both covered.
- The upload path validates normalized content again on the server.
- The sidebar and settings use one rendering component.
- Each production unit has a preceding failing test step.
- Final checks cover unit, integration, lint, i18n, build, browser behavior, git
  scope, remote sync, and PR creation.
