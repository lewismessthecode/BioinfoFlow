import { expect, test, type Locator } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import {
  createKeylessAgentSession,
  setupKeylessAgentModel,
} from "./support/keyless-agent"

const historyMessage = Array.from(
  { length: 240 },
  (_, index) => `History item ${index + 1} establishes a scrollable transcript.`,
).join(" ")

test.describe("Agent transcript scrolling", () => {
  test("jumps to the latest content and follows subsequent streamed output", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(
      request,
      "streaming-scroll",
      testInfo,
    )
    const opened = await createKeylessAgentSession(request, { modelId })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage(historyMessage)
    await expect(
      agent.transcript.getByText("This streamed line 100 extends the response."),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.activeRun).toHaveCount(0, { timeout: 20_000 })

    await expect
      .poll(() =>
        agent.transcript.evaluate((element) =>
          element.scrollHeight > element.clientHeight,
        ),
      )
      .toBe(true)
    await agent.transcript.evaluate((element) => {
      element.scrollTop = 0
      element.dispatchEvent(new Event("scroll", { bubbles: true }))
    })

    await agent.sendMessage("Start another response while I read the history.")
    await expect(agent.activeRun).toBeVisible({ timeout: 20_000 })
    const jumpToLatest = page.getByRole("button", {
      name: "Jump to latest",
      exact: true,
    })
    await expect(jumpToLatest).toBeVisible()
    await expect(
      agent.transcript.getByText("The streamed response is starting.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })

    await jumpToLatest.click()
    await expect
      .poll(() => scrollPosition(agent.transcript))
      .toMatchObject({ atBottom: true })
    await expect(jumpToLatest).toBeHidden()

    await expect(
      agent.transcript.getByText("This streamed line 100 extends the response."),
    ).toHaveCount(2, { timeout: 20_000 })
    await expect(agent.activeRun).toHaveCount(0, { timeout: 20_000 })
    await expect(page.getByTestId("agent-run-outcome")).toHaveCount(0)
    await expect
      .poll(() => scrollPosition(agent.transcript))
      .toMatchObject({ atBottom: true })
  })
})

async function scrollPosition(transcript: Locator) {
  return transcript.evaluate((element) => ({
    atBottom:
      element.scrollHeight - element.scrollTop - element.clientHeight <= 1,
    scrollHeight: element.scrollHeight,
    scrollTop: element.scrollTop,
  }))
}
