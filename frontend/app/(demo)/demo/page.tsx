import { readFileSync } from "node:fs"
import { join } from "node:path"

import { DemoPageClient } from "./demo-page-client"

export default function DemoPage() {
  const recording = readFileSync(
    join(process.cwd(), "lib/demo/recordings/rnaseq-quant-mini-run.ndjson"),
    "utf-8",
  )
  return <DemoPageClient recording={recording} />
}
