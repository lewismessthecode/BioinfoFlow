"use client"

import type { ReactNode } from "react"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"

interface SidebarDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}

export function SidebarDrawer({ open, onOpenChange, children }: SidebarDrawerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="fixed inset-y-0 left-0 !flex h-[100dvh] w-[300px] max-w-[86vw] translate-x-0 translate-y-0 !flex-col !gap-0 rounded-none border-r border-sidebar-border bg-sidebar p-0 data-[state=open]:animate-in data-[state=open]:slide-in-from-left data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left duration-200"
        style={{ maxHeight: "100dvh" }}
      >
        <VisuallyHidden>
          <DialogTitle>Navigation</DialogTitle>
        </VisuallyHidden>
        {children}
      </DialogContent>
    </Dialog>
  )
}
