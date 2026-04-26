import { screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import RunDetailPage from "@/app/(app)/runs/[runId]/page"
import { createDemoRuntime, setActiveRuntimeForTests } from "@/lib/runtime"
import { renderAppPage } from "@/tests/app-test-utils"

const paramsState = {
  runId: "run_demo_001",
}
const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

let demoRuntime: ReturnType<typeof createDemoRuntime>

vi.mock("next/navigation", () => ({
  useParams: () => ({ runId: paramsState.runId }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    if (!translationMocks.has(namespace)) {
      translationMocks.set(
        namespace,
        (key: string, values?: Record<string, unknown>) => {
          const suffix = values
            ? Object.values(values)
                .filter((value) => value !== undefined && value !== null)
                .join(":")
            : ""
          return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
        },
      )
    }

    return translationMocks.get(namespace)!
  },
}))

vi.mock("next/dynamic", () => ({
  default: () => () => null,
}))

vi.mock("@/app/(app)/runs/components/run-detail-content", () => ({
  RunDetailContent: ({
    run,
    outputs,
    logs,
    dag,
  }: {
    run: { run_id: string; status: string }
    outputs: { files?: unknown[] } | null
    logs: { logs?: unknown[] } | null
    dag: { nodes?: unknown[] } | null
  }) => (
    <div data-testid="run-detail-content">
      {run.run_id}:status:{run.status}:outputs:{outputs?.files?.length ?? 0}:logs:
      {logs?.logs?.length ?? 0}:dag:{dag?.nodes?.length ?? 0}
    </div>
  ),
}))

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe("RunDetailPage under demo runtime", () => {
  beforeEach(async () => {
    vi.stubEnv("APP_RUNTIME", "demo")
    vi.stubEnv("DEPLOY_MODE", "demo")
    demoRuntime = createDemoRuntime()
    setActiveRuntimeForTests(demoRuntime)
    const response = await demoRuntime.request<{ run_id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-demo",
        workflow_id: "wf-rnaseq-quant-mini",
        values: {
          reads_r1: "deliveries/ecoli_R1.fastq.gz",
          reads_r2: "deliveries/ecoli_R2.fastq.gz",
          reference: "reference/ecoli_k12.fa",
        },
      }),
    })
    paramsState.runId = response.data.run_id
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    setActiveRuntimeForTests(null)
  })

  it(
    "hydrates the run detail tabs from demo data and refreshes artifacts as the replay completes",
    async () => {
      renderAppPage(<RunDetailPage />, {
        projectContext: {
          activeProjectId: "",
          selectedProjectId: "",
          conversationProjectId: "",
        },
      })

      expect(await screen.findByTestId("run-detail-content")).toHaveTextContent(
        "run_demo_001:status:pending:outputs:3:logs:0:dag:3",
      )

      await waitFor(
        () => {
          expect(screen.getByTestId("run-detail-content")).toHaveTextContent(
            "run_demo_001:status:completed:outputs:3:logs:3:dag:3",
          )
        },
        { timeout: 7000 },
      )
    },
    10000,
  )
})
