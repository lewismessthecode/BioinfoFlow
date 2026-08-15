import { expect, test } from "@playwright/test"

import {
  createKeylessAgentSession,
  dispatchKeylessAgentMessage,
  getKeylessAgentSnapshot,
  setupKeylessAgentModel,
} from "./keyless-agent"

test("the local fake model completes a real Agent Harness run without provider keys", async ({
  request,
}, testInfo) => {
  const modelId = await setupKeylessAgentModel(request, "streaming", testInfo)
  const opened = await createKeylessAgentSession(request, { modelId })
  const sessionId = opened.session.id

  await dispatchKeylessAgentMessage(request, sessionId, "Explain the keyless test path.")

  await expect
    .poll(
      async () => {
        const snapshot = await getKeylessAgentSnapshot(request, sessionId)
        return snapshot.runs.at(-1)?.status
      },
      { timeout: 20_000 },
    )
    .toBe("completed")

  const completed = await getKeylessAgentSnapshot(request, sessionId)
  expect(JSON.stringify(completed.entries)).toContain(
    "Keyless model stream completed.",
  )
})
