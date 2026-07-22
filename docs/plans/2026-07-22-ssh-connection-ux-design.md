# SSH Connection UX Refinement Design

## Problem

The connection page currently treats persistence and reachability as separate user tasks. Saving a new or edited SSH host leaves it in the `unknown` state until the user opens the overflow menu and manually chooses **Test connection**. This makes a valid host appear unusable even though the application already has everything required to verify it.

The **Run check** action also lacks durable feedback. Its loading label lives inside a dropdown that closes as soon as the action starts, while command output is rendered near the bottom of a scrollable drawer. A user who remains near the top sees no meaningful state change.

## Principles

1. **The user's goal is a usable host, not a saved database row.** Persistence should be followed immediately by reachability verification.
2. **Status should be evidence from an actual connection attempt.** A manual test is a retry and diagnostic tool, not a prerequisite for making the host usable.
3. **Every action needs an immediate, persistent response.** Feedback must remain visible after a dropdown closes and must distinguish running, success, and failure.
4. **Prefer the smallest complete change.** Reuse the existing create, update, test, and command-stream APIs. Do not add jobs, polling, or new backend state.

## Reference Interaction Model

Traditional SSH clients save host configuration independently, then initiate a real connection when the user connects. They do not require a separate test ritual before the host can be used. Connection-manager products, including Codex-style SSH connection surfaces, similarly derive availability from attempted connection and keep manual testing as a retry or troubleshooting affordance.

Bioinfoflow should combine the two steps after form submission: save first, then automatically verify. The saved host remains available even if verification fails so the user can edit credentials or retry.

## Proposed Experience

### Save and automatic verification

1. The user submits a new or edited host.
2. Bioinfoflow saves it with the existing API.
3. The drawer closes and the host card appears immediately.
4. The card shows a transient `Connecting...` state while the existing test endpoint runs.
5. A successful test updates the card to `Online` and shows a success toast.
6. A failed test updates the persisted status returned by the test endpoint when available and shows an error toast. The saved host is not removed.
7. A transport-level test failure clears the transient state and leaves the last persisted status visible.

Editing a host follows the same flow because changes to address, port, username, or credentials can invalidate prior reachability evidence.

### Manual retry

The existing overflow action remains available, but its label becomes **Retest connection** / **重新测试连接**. While active, the corresponding card also shows `Connecting...`, so feedback remains visible after the menu closes.

### Run check feedback

Starting **Run check** immediately renders a persistent live region directly below the drawer header. It contains:

- a spinner and `Running connection check...` while the command is active;
- a success icon and `Connection check completed.` after exit code `0`;
- an error icon and a failure message after a non-zero exit, timeout, WebSocket error, or early close.

The existing output panel remains the detailed result. The summary is intentionally short and does not introduce progress percentages or a multi-step diagnostic workflow.

## State Model

Persisted host status remains unchanged: `unknown | online | offline | error`.

Two frontend-only transient states are sufficient:

- `testingConnectionId`: identifies the card currently being verified;
- `probeState`: `idle | running | success | error` plus an optional summary message.

No new backend schema or API is needed.

## Accessibility

- Transient card text is exposed as normal status text instead of relying only on animation or color.
- The run-check summary uses `role="status"` while running/successful and `role="alert"` on failure.
- The spinner respects the existing reduced-motion behavior through the shared icon animation conventions.
- English and Simplified Chinese messages are updated together.

## Testing

Integration tests will prove:

1. Creating a host calls the test endpoint automatically and renders `Connecting...` before the test resolves.
2. Editing a host also triggers automatic verification.
3. A failed automatic test keeps the host in the list and surfaces the failure.
4. Manual verification exposes the transient state outside the closed dropdown.
5. Run check immediately renders a visible running summary and then a completion summary with output.
6. Run-check stream failures render an alert.

The final verification set is `bun run lint`, `bun run lint:i18n`, `bun run lint:dead-code`, `bun run test`, and `bun run build` from `frontend/`.
