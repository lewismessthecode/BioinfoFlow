"use client"

import Link from "next/link"
import dynamic from "next/dynamic"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { ExternalLink } from "@/lib/icons"

const LlmCatalogPanel = dynamic(
  () =>
    import("@/components/bioinfoflow/settings/llm-catalog-panel").then(
      (module) => module.LlmCatalogPanel,
    ),
  { loading: ProviderCatalogLoading },
)

type AgentModelConnectionDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function ProviderCatalogLoading() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true">
      <Skeleton className="h-8 w-36" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-28 w-full" />
    </div>
  )
}

export function AgentModelConnectionDialog({
  open,
  onOpenChange,
}: AgentModelConnectionDialogProps) {
  const t = useTranslations("agentWorkbench")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100svh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b px-6 py-5 pr-14">
          <DialogTitle>{t("modelConnection.title")}</DialogTitle>
          <DialogDescription>
            {t("modelConnection.description")}
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 overscroll-contain overflow-y-auto px-4 py-4 sm:px-6">
          <LlmCatalogPanel />
        </div>
        <DialogFooter className="border-t px-4 py-3 sm:px-6">
          <Button asChild variant="outline" size="sm">
            <Link
              href="/settings?section=providers"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("modelConnection.fullSettings")}
              <ExternalLink data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
