import { expect, test } from "@playwright/test"

import { SettingsPage } from "./pages/settings-page"

test.describe("Settings provider journey", () => {
  test("persists a Responses provider and tests the explicitly selected model", async ({
    page,
  }, testInfo) => {
    const settings = new SettingsPage(page)
    const providerLabel = "OpenAI Compatible"
    const model = `responses-e2e-${testInfo.retry}`
    const apiKey = `sk-write-only-${testInfo.retry}`
    const endpoint = `http://responses-${testInfo.retry}.example.invalid/v1`
    const discoverRequests: string[] = []
    let testedModelId: string | undefined
    let probeAttempt = 0

    page.on("request", (request) => {
      if (request.url().includes("/discover-models")) {
        discoverRequests.push(request.url())
      }
    })
    await page.route("**/api/v1/llm/providers/*/test", async (route) => {
      const payload = route.request().postDataJSON() as { model_id?: string }
      testedModelId = payload.model_id
      probeAttempt += 1
      const success = probeAttempt === 1
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: {
            provider_id: "e2e-provider",
            success,
            model,
            wire_protocol: "responses",
            error_code: success ? null : "authentication",
            error: success ? null : "Authentication failed",
            latency_ms: success ? 37 : 12,
            retryable: false,
            http_status: success ? null : 401,
            provider_code: null,
          },
        }),
      })
    })

    await settings.goto()
    await settings.expectLoaded()
    await settings.openProvidersSection()

    await settings.saveField(providerLabel, "Endpoint", endpoint)
    await settings.saveField(providerLabel, "API key", apiKey)
    await settings.saveField(providerLabel, "Model ID", model)
    await settings.chooseProtocol(providerLabel, "Responses")
    await settings.allowInsecureHttp(providerLabel)

    await expect(settings.saveButton(providerLabel)).toBeVisible()
    await expect(settings.discoverButton()).toBeVisible()
    await expect(settings.testButton(providerLabel)).toHaveCount(0)

    const setupResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes("/api/v1/llm/provider-setups"),
    )
    await settings.clickSave(providerLabel)
    const setupResponse = await setupResponsePromise
    expect(setupResponse.ok()).toBeTruthy()
    const setupPayload = await setupResponse.json()
    const expectedModelId = setupPayload.data.models[0].id
    expect(discoverRequests).toEqual([])

    await page.reload()
    await settings.expectLoaded()
    await settings.openProvidersSection()
    await settings.expectProtocol(providerLabel, "Responses")
    await settings.expectWriteOnlyKey(providerLabel)
    await expect(settings.testButton(providerLabel)).toBeVisible()
    await expect(
      settings.providerCard(providerLabel).getByText("Insecure transport allowed"),
    ).toBeVisible()

    await settings.chooseTestModel(providerLabel, model)
    await settings.clickTest(providerLabel)
    expect(testedModelId).toBe(expectedModelId)
    await settings.expectTestStatus(
      providerLabel,
      /Connection verified.*Responses.*37\s*ms|Responses.*Connection verified.*37\s*ms/s,
    )

    await settings.clickTest(providerLabel)
    await settings.expectTestStatus(providerLabel, /Connection failed.*Authentication failed/s)
    await expect(page.getByText(apiKey)).toHaveCount(0)
  })
})
