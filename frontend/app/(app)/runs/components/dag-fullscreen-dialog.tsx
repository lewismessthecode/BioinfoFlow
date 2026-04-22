"use client"

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { DagPanel } from "@/components/bioinfoflow/dag"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"
import type { DagData } from "@/lib/types"

interface DagFullscreenDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  runId: string
  dag: DagData | null
  workflowName: string
}

export function DagFullscreenDialog({
  open,
  onOpenChange,
  runId,
  dag,
  workflowName,
}: DagFullscreenDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[calc(100vw-4rem)] h-[calc(100vh-4rem)] p-0 flex flex-col gap-0"
        showCloseButton
      >
        <VisuallyHidden>
          <DialogTitle>Pipeline DAG — {workflowName}</DialogTitle>
        </VisuallyHidden>
        <div className="flex-1 min-h-0">
          <DagPanel
            variant="embedded"
            runId={runId}
            dag={dag}
            theme="classic"
            workflowName={workflowName}
            showHeader={false}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
