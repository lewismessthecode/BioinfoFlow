import { readFileSync } from "node:fs"
import { join } from "node:path"
import { DemoShell } from "./demo-shell"
import type { ReactNode } from "react"

export const metadata = {
  title: "Bioinfoflow Demo",
  description: "See Bioinfoflow in action — AI-driven bioinformatics pipeline execution",
}

function loadRecording(): string {
  const filePath = join(process.cwd(), "lib/demo/recordings/rnaseq-quant-mini-run.ndjson")
  return readFileSync(filePath, "utf-8")
}

export default function DemoLayout({ children }: { children: ReactNode }) {
  const recording = loadRecording()

  return (
    <DemoShell recording={recording}>
      {children}
    </DemoShell>
  )
}
