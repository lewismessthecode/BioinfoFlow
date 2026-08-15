import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import {
  createKeylessAgentSession,
  restartKeylessBackend,
  setupKeylessAgentModel,
} from "./support/keyless-agent"

test.describe("Agent interaction journey", () => {
  test("approves a guarded tool call and resumes the same run", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "approval", testInfo)
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "ask_changes",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Create the keyless approval marker.")

    await expect(agent.approvalCard).toBeVisible({ timeout: 20_000 })
    await expect(agent.approvalCard).toContainText("Allow this tool to run?")
    await expect(agent.approvalCard).toContainText("e2e-approved.txt")
    await expect(
      agent.approvalCard.getByRole("button", { name: "Approve", exact: true }),
    ).toBeVisible()

    await agent.approvalCard
      .getByRole("button", { name: "Approve", exact: true })
      .click()

    await expect(
      agent.transcript.getByText("Approval scenario completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.transcript.getByText("Approved", { exact: true }),
    ).toBeVisible()
  })

  test("answers an agent question and resumes the same run", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "ask-user", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Ask me whether the keyless run should continue.")

    await expect(agent.askUserCard).toBeVisible({ timeout: 20_000 })
    await expect(agent.askUserCard).toContainText(
      "Should the keyless run continue?",
    )
    await agent.askUserCard.getByRole("radio", { name: /Continue/ }).check()
    await agent.askUserCard
      .getByRole("button", { name: "Submit answers", exact: true })
      .click()

    await expect(
      agent.transcript.getByText("The keyless answer was received.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.transcript.getByText("Answered", { exact: true }),
    ).toBeVisible()
  })

  test("stops a running tool and returns the composer to idle", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "stop", testInfo)
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Start the long keyless task so I can stop it.")

    await expect(
      agent.activeRun.getByText("Run command", { exact: true }),
    ).toBeVisible({
      timeout: 20_000,
    })
    await expect(agent.stopButton).toBeVisible()
    await agent.stopButton.click()

    await expect(agent.activeRun).toHaveCount(0, { timeout: 20_000 })
    await expect(
      agent.transcript
        .getByTestId("agent-run-outcome")
        .filter({ hasText: "Cancelled" }),
    ).toBeVisible()
    await expect(agent.sendButton).toBeVisible()
    await expect(
      agent.transcript.getByText("Stop scenario completed.", { exact: true }),
    ).toHaveCount(0)
  })

  test("reconnects the Session stream after a network interruption", async ({
    context,
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "streaming", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await expect(
      page.getByLabel("Connected", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })

    await context.setOffline(true)
    await expect(
      page.getByText(
        "You are offline. The conversation will resume when the connection returns.",
        { exact: true },
      ).first(),
    ).toBeVisible({ timeout: 10_000 })

    await context.setOffline(false)
    await expect(
      page.getByLabel("Connected", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
  })

  test("recovers an interrupted tool after a backend restart", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "recovery", testInfo)
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Start the restart recovery scenario.")
    await expect(
      agent.activeRun.getByText("Run command", { exact: true }),
    ).toBeVisible({
      timeout: 20_000,
    })

    await restartKeylessBackend(request)

    await page.reload()
    await expect(agent.recoveryCard).toBeVisible({ timeout: 20_000 })
    await agent.recoveryCard
      .getByRole("button", { name: "Inspect state", exact: true })
      .click()
    await expect(
      agent.transcript.getByText("Recovered after inspection.", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.recoveryCard.getByText("Inspect state", { exact: true }),
    ).toBeVisible()
    await expect(agent.activeRun).toHaveCount(0)
    await agent.expectComposerReady()
  })
})
