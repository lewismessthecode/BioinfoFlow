import { readFileSync } from "node:fs"
import { join } from "node:path"
import { DemoShell } from "./demo-shell"
import type { ReactNode } from "react"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Bioinfoflow Demo | AI Bioinformatics Pipeline Walkthrough",
  description:
    "Watch Bioinfoflow turn a research request into a reproducible bioinformatics pipeline with chat, DAG visualization, logs, and local-first execution.",
  alternates: { canonical: "/demo" },
  openGraph: {
    title: "Bioinfoflow Demo",
    description:
      "Watch Bioinfoflow turn a research request into a reproducible bioinformatics pipeline with chat, DAG visualization, logs, and local-first execution.",
    url: "/demo",
    siteName: "Bioinfoflow",
    images: [{ url: "/image.png", width: 1024, height: 1024, alt: "Bioinfoflow demo interface" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Bioinfoflow Demo",
    description:
      "Watch Bioinfoflow turn a research request into a reproducible bioinformatics pipeline with chat, DAG visualization, logs, and local-first execution.",
    images: ["/image.png"],
  },
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
