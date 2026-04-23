import { expect, test } from "@playwright/test"
import { SettingsPage } from "./pages/settings-page"

test.describe("Settings provider journey", () => {
  test("saves provider settings and surfaces successful and failed test feedback", async ({
    page,
  }, testInfo) => {
    const settings = new SettingsPage(page)
    const ollamaBaseUrl = `http://127.0.0.1:${11434 + testInfo.retry}`
    const ollamaModel = `llama3.3-e2e-${testInfo.retry}`
    const openAiKey = `sk-e2e-openai-test-key-${testInfo.retry}`
    const openAiBaseUrl = `http://127.0.0.1:9/e2e-${testInfo.retry}/v1`

    await settings.goto()
    await settings.expectLoaded()
    await settings.openProvidersSection()

    await settings.saveField("Ollama", "Base URL", ollamaBaseUrl)
    await expect(page.getByText("Base URL saved")).toBeVisible()
    await settings.saveField("Ollama", "Model", ollamaModel)
    await expect(page.getByText("Model saved")).toBeVisible()

    await expect(settings.testButton("Ollama")).toBeEnabled()
    await settings.clickTest("Ollama")
    await expect(page.getByText("Connection successful")).toBeVisible()
    await settings.expectSuccessState("Ollama")

    await settings.saveField("OpenAI", "API Key", openAiKey)
    await expect(page.getByText("API key saved")).toBeVisible()
    await settings.saveField("OpenAI", "Base URL", openAiBaseUrl)
    await expect(page.getByText("Base URL saved")).toBeVisible()

    await expect(settings.testButton("OpenAI")).toBeEnabled()
    await settings.clickTest("OpenAI")
    await settings.expectFailureState("OpenAI")
  })
})
