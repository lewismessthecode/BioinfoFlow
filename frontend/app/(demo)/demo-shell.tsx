"use client"

import type { ReactNode } from "react"
import { DemoReplayProvider } from "@/lib/demo/demo-context"

export function DemoShell({
  recording,
  children,
}: {
  recording: string
  children: ReactNode
}) {
  return (
    <DemoReplayProvider recording={recording} autoPlay>
      <div className="flex h-dvh flex-col bg-background text-foreground">
        {children}
      </div>
    </DemoReplayProvider>
  )
}
