# Pixel Default Avatars Design

## Status

Approved direction for implementation on 2026-07-20.

## Problem

The user control at the bottom of the Bioinfoflow sidebar currently shows a
remote profile image when one exists and falls back to initials otherwise. The
initials are functional but generic, visually weak at 32 pixels, and do not give
users a memorable identity inside the product.

Bioinfoflow needs a small family of distinctive default avatars and a simple
account setting for changing them. The feature should feel designed for
Bioinfoflow without becoming a character editor or introducing an external
avatar service.

## Decisions

- Use a curated collection of 18 to 24 handcrafted SVG avatars instead of a
  combinatorial generator.
- Use the approved **Pixel Personas / Lab Personalities** direction: restrained
  12-by-12 pixel portraits with professional expressions and occasional subtle
  details such as glasses, a lab cap, a headset, or a small hair accessory.
- Keep the current rounded-square avatar shape. Do not switch to circular
  portraits.
- Assign an unchanged user a stable default avatar derived from the user ID.
  “Random” means varied across users, not different on every render.
- Let users choose another curated avatar, request another candidate set, upload
  a custom image, or restore the deterministic default.
- Do not add per-feature editing for hair, expression, accessories, skin tone,
  or colors.
- Do not call an external avatar API at runtime.

## Visual System

Each built-in avatar uses the same small pixel grid and a deliberately limited
palette. Distinction comes from three controlled dimensions:

1. portrait silhouette and hair shape;
2. one of 8 to 12 reviewed color palettes;
3. at most one memorable detail on a minority of portraits.

The collection must be reviewed at the actual 32-pixel sidebar size. Large
preview quality is secondary. Pixel edges remain crisp, facial features remain
legible in light and dark themes, and no avatar depends on texture that
disappears when reduced.

The portraits should be inclusive without attempting to infer or encode a
user’s identity from their name, email, or profile data. The deterministic seed
selects a finished portrait; it does not derive gender, ethnicity, age, or role.

## Avatar Resolution

Profile image resolution follows this order:

1. a valid uploaded custom image;
2. a user-selected built-in avatar;
3. the deterministic built-in avatar derived from the stable viewer ID;
4. the existing initials fallback if an image cannot be resolved or loaded.

The built-in catalog has stable keys such as `pixel-persona-01`. A small pure
resolver hashes the viewer ID and maps it to a catalog entry. The resolver must
produce the same result in server and client rendering and must not use
`Math.random()`.

Built-in avatars are local SVG assets shipped with the frontend. Selecting one
stores its stable asset reference in the existing Better Auth `user.image`
field. A null image continues to mean “use my deterministic default,” avoiding
a database write merely to show a default avatar.

## Account Settings Experience

The existing Account section gains an avatar group above the email and role
rows.

The group contains:

- a 72-pixel preview of the active avatar;
- the current user name and a short explanation;
- a grid of six built-in candidates at a time;
- a **Show another set** action that rotates through the curated catalog without
  saving anything;
- an **Upload image** action;
- a **Restore default** action when the user has made a selection or upload.

Clicking a built-in candidate saves immediately and updates both the settings
preview and sidebar user control. The selected candidate has a visible border
and an accessible selected state. “Show another set” changes only the visible
choices; it never changes the active avatar by itself.

The upload flow accepts PNG, JPEG, and WebP. The client presents a compact
square crop dialog, produces a 256-by-256 WebP preview, and submits only after
the user confirms. The dialog supports zoom and repositioning but no filters or
decorative editing.

## Persistence And Storage

For authenticated personal and team modes, custom avatar files are stored under
the shared Bioinfoflow state root rather than in the repository. The upload
handler:

- requires a valid Better Auth session;
- validates file type and byte limits;
- writes one normalized file per user atomically;
- returns a Bioinfoflow-owned URL with a cache-busting version;
- updates `user.image` only after the file write succeeds;
- removes a superseded upload after the new profile reference is durable.

The route serving uploaded avatars requires authentication and must prevent path
traversal or arbitrary file access. File names are derived from a safe digest of
the user ID, not from user-supplied names.

In unauthenticated development mode, the built-in choice is browser-local. A
cropped custom avatar may also be stored browser-locally after normalization.
This keeps visual verification and local use functional without introducing a
fake Better Auth user.

## Component Boundaries

- `pixel-persona-catalog` owns stable avatar keys, asset paths, and deterministic
  selection. It has no React or storage dependencies.
- `use-resolved-avatar` resolves explicit, development-local, and deterministic
  avatar sources for UI consumers.
- `UserMenu` renders the resolved avatar and retains the existing initials
  fallback.
- The Account settings avatar panel owns candidate pagination, upload dialog
  state, save feedback, and reset actions.
- The authenticated avatar route owns validation, file persistence, and profile
  updates. UI components never write directly to the filesystem.

## Data Flow

### Default display

```text
viewer ID + viewer image
  -> avatar resolver
  -> explicit image or deterministic catalog asset
  -> UserMenu / Account preview
  -> initials only if image loading fails
```

### Built-in selection

```text
select catalog item
  -> Better Auth updateUser(image) or development-local preference
  -> refresh viewer state
  -> sidebar and settings render the same asset
```

### Custom upload

```text
select file
  -> validate and crop in browser
  -> normalize to 256 x 256 WebP
  -> authenticated upload route
  -> atomically persist file
  -> update Better Auth user.image
  -> refresh viewer state
```

## Failure Behavior

- A broken or missing image displays the deterministic avatar, then initials if
  that asset also fails.
- A rejected upload explains whether the file type, dimensions, or size caused
  the rejection and leaves the current avatar unchanged.
- A failed profile update does not delete the previously active upload.
- Rapid repeated saves disable conflicting controls until the active request
  finishes.
- Candidate browsing is entirely local and cannot fail because of network or
  avatar service availability.

## Accessibility And Localization

- Avatar choice controls use radio-style selected semantics and visible focus
  rings.
- Decorative avatars use empty alternative text; account controls have explicit
  localized labels.
- Status is not communicated by color alone.
- New copy is added to both `frontend/messages/en.json` and
  `frontend/messages/zh-CN.json` and verified with the i18n lint.

## Testing

- Unit-test stable hash mapping, catalog boundaries, and deterministic fallback.
- Test `UserMenu` with an upload, a selected built-in asset, a deterministic
  default, and an image load failure.
- Extend Account settings tests for candidate browsing, selection, reset,
  upload validation, successful upload, and failed save behavior.
- Test avatar routes for authentication, supported and rejected media, size
  limits, safe file names, replacement, and missing files.
- Run frontend lint, i18n lint, relevant unit and integration tests, and the full
  frontend test suite when the implementation blast radius is confirmed.

## Non-Goals

- Infinite procedural avatar combinations.
- A full avatar or character editor.
- Animated avatars.
- User-generated accessories or palettes.
- External runtime avatar APIs.
- Team administrators assigning avatars to other users in this iteration.

## Reference Principles

The design borrows the stable-seed behavior used by identicon systems and the
local deterministic generation model used by DiceBear and Boring Avatars. The
visual assets themselves are Bioinfoflow-specific and will not copy those
libraries’ artwork.
