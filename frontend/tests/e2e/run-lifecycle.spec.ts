import { expect, test } from "@playwright/test"
import { RunsPage } from "./pages/runs-page"
import {
  findLatestResumedRunId,
  readRunStatus,
  runLifecycleFixture,
  seedRunLifecycleFixture,
} from "./support/run-lifecycle-db"

test.describe("Run lifecycle journey", () => {
  test.beforeEach(async () => {
    seedRunLifecycleFixture()
  })

  test("resumes a failed run and cancels the queued retry from the Runs page", async ({ page }) => {
    const runs = new RunsPage(page)

    await runs.goto(runLifecycleFixture.projectId)
    await runs.expectLoaded()
    await runs.expectRunCount(1)
    await runs.expectRunVisible(runLifecycleFixture.failedRunId)
    await runs.expectRunStatus(runLifecycleFixture.failedRunId, "Failed")

    await runs.resumeRun(runLifecycleFixture.failedRunId)

    await expect(page.getByText(`${runLifecycleFixture.failedRunId} resumed`)).toBeVisible()
    await expect(page.getByText("Pipeline execution queued")).toBeVisible()
    await runs.expectRunCount(2)

    let resumedRunId: string | null = null
    await expect
      .poll(() => {
        resumedRunId = findLatestResumedRunId()
        return resumedRunId
      }, {
        message: "expected the resume action to create a new queued run",
      })
      .not.toBeNull()

    if (!resumedRunId) {
      throw new Error("Resume action did not create a follow-up run")
    }

    await runs.expectRunVisible(resumedRunId)
    await runs.expectRunStatus(resumedRunId, "Queued")
    await expect.poll(() => readRunStatus(resumedRunId)).toBe("queued")

    await runs.cancelRun(resumedRunId)
    await runs.confirmCancel()

    await expect(page.getByText(`${resumedRunId} cancelled`)).toBeVisible()
    await expect(page.getByText("Pipeline execution stopped")).toBeVisible()
    await runs.expectRunStatus(resumedRunId, "Cancelled")
    await expect.poll(() => readRunStatus(resumedRunId)).toBe("cancelled")
  })
})
