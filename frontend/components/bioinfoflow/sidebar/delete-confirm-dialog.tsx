"use client"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface DeleteConfirmState {
  type: "project" | "conversation"
  id: string
  projectId: string
  name: string
}

interface DeleteConfirmDialogProps {
  deleteConfirm: DeleteConfirmState | null
  onCancel: () => void
  onConfirm: () => void
  tSidebar: (key: string, values?: Record<string, string>) => string
  tCommon: (key: string) => string
}

export function DeleteConfirmDialog({
  deleteConfirm,
  onCancel,
  onConfirm,
  tSidebar,
  tCommon,
}: DeleteConfirmDialogProps) {
  return (
    <Dialog open={!!deleteConfirm} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>
            {deleteConfirm?.type === "project"
              ? tSidebar("toasts.deleteProjectConfirmTitle", { name: deleteConfirm?.name ?? "" })
              : tSidebar("toasts.deleteConversationConfirmTitle")}
          </DialogTitle>
          <DialogDescription>{tCommon("cannotUndo")}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onCancel}>
            {tCommon("cancel")}
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            {tCommon("delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
