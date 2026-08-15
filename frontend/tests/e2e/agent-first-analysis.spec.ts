import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import {
  createKeylessAgentSession,
  setupKeylessAgentModel,
} from "./support/keyless-agent"

test.describe("Agent workbench live run journey", () => {
  test("creates a Session on the first browser message", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    await setupKeylessAgentModel(request, "streaming", testInfo)
    const prompt = "Explain the keyless browser test path."

    await agent.goto()
    await agent.expectComposerReady()
    await agent.sendMessage(prompt)
    await agent.expectSessionRoute()

    await expect(
      agent.transcript.getByText(prompt, { exact: true }),
    ).toBeVisible()
    await expect(
      agent.transcript.getByText("Keyless model stream completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.transcript.getByText("Thinking summary", { exact: true }),
    ).toBeVisible()
  })

  test("streams thinking and the final answer through the real Agent Harness", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "streaming", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })
    const prompt = "Show the live keyless stream."

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage(prompt)

    await expect(
      agent.transcript.getByText(prompt, { exact: true }),
    ).toBeVisible()
    await expect(agent.activeRun.getByText("Thinking summary")).toBeVisible({
      timeout: 20_000,
    })
    await expect(
      agent.activeRun.getByText("Checking the keyless request.", {
        exact: true,
      }),
    ).toBeVisible()
    await expect(
      agent.activeRun.getByText("Keyless model", { exact: true }),
    ).toBeVisible()
    await expect(
      agent.transcript.getByText("Keyless model stream completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.activeRun).toHaveCount(0)
    await expect(
      agent.transcript.getByText("Finished", { exact: false }),
    ).toBeVisible()
  })

  test("renders a structured plan without a duplicate tool card", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "plan", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Show a plan before continuing.")

    await expect(
      agent.transcript.getByRole("heading", { name: "Keyless execution plan" }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.transcript.getByText("Inspect the request")).toBeVisible()
    await expect(agent.transcript.getByText("Summarize the result")).toBeVisible()
    await expect(
      agent.transcript.getByText("The keyless plan is ready.", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.transcript.getByText("update_plan")).toHaveCount(0)
  })

  test("groups concurrent tool calls into one parallel activity", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(
      request,
      "parallel-tools",
      testInfo,
    )
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Read both keyless values in parallel.")

    await expect(
      agent.transcript.getByText("Both keyless tools completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.activityGroups).toHaveCount(1)
    await expect(
      agent.activityGroups.getByRole("button", {
        name: "2 tools running in parallel",
      }),
    ).toBeVisible()
  })

  test("labels an ordered tool batch as sequential activity", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "serial-tools", testInfo)
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Run both keyless shell inspections in sequence.")

    await expect(
      agent.transcript.getByText("Both serial tools completed.", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.activityGroups.getByRole("button", {
        name: "2 tools running in sequence",
      }),
    ).toBeVisible()
  })
})
