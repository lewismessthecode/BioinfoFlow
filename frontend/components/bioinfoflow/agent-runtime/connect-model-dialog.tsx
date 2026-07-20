"use client"

import Link from "next/link"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"

import { ProviderIcon } from "@/components/bioinfoflow/chat/provider-icons"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useLlmCatalog } from "@/hooks/use-llm-catalog"
import type { ModelSelection } from "@/hooks/use-llm-settings"
import {
  useProviderConnection,
  type ProviderConnectionOutcome,
} from "@/hooks/use-provider-connection"
import { cn } from "@/lib/utils"

const QUICK_PROVIDER_IDS = ["openai", "anthropic", "deepseek"] as const

type ConnectModelDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  setSelectedModel: (selection: ModelSelection | null) => Promise<void>
  refreshSettings: () => Promise<void>
  onConnected: () => void
}

export function ConnectModelDialog({
  open,
  onOpenChange,
  setSelectedModel,
  refreshSettings,
  onConnected,
}: ConnectModelDialogProps) {
  const t = useTranslations("agentRuntime")
  const {
    providerTemplates = [],
    isLoading: catalogLoading,
    error: catalogError,
    refresh: refreshCatalog,
    setupProvider,
    discoverModels,
    testProvider,
  } = useLlmCatalog()
  const connectionOperations = useMemo(
    () => ({
      setupProvider,
      discoverModels,
      testProvider,
      activation: {
        mode: "activate" as const,
        setSelectedModel,
        refreshSettings,
      },
    }),
    [
      discoverModels,
      refreshSettings,
      setSelectedModel,
      setupProvider,
      testProvider,
    ],
  )
  const { connect, isConnecting } = useProviderConnection(connectionOperations)
  const quickProviders = useMemo(
    () =>
      QUICK_PROVIDER_IDS.flatMap((id) => {
        const template = providerTemplates.find((item) => item.id === id)
        return template ? [template] : []
      }),
    [providerTemplates],
  )
  const [selectedTemplateId, setSelectedTemplateId] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [failure, setFailure] = useState<ProviderConnectionOutcome | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const wasOpen = useRef(false)

  useEffect(() => {
    if (open && !wasOpen.current) {
      setSelectedTemplateId("")
      setApiKey("")
      setFailure(null)
    }
    wasOpen.current = open
  }, [open])

  useEffect(() => {
    if (!open || selectedTemplateId || quickProviders.length === 0) return
    setSelectedTemplateId(quickProviders[0].id)
  }, [open, quickProviders, selectedTemplateId])

  const submit = async () => {
    if (!selectedTemplateId || !apiKey.trim() || submitting || isConnecting) return
    setFailure(null)
    setSubmitting(true)
    try {
      const outcome = await connect({
        templateId: selectedTemplateId,
        apiKey: apiKey.trim(),
      })
      if (!outcome.ok) {
        setFailure(outcome)
        return
      }
      onOpenChange(false)
      onConnected()
    } finally {
      setSubmitting(false)
    }
  }

  const failureStage = failure && !failure.ok ? failure.stage : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[400px] gap-4 rounded-[8px] border-border/80 p-5 shadow-[0_8px_24px_rgba(17,17,17,0.04)]">
        <DialogHeader className="gap-1.5 pr-6">
          <DialogTitle className="text-[16px] tracking-[-0.01em]">
            {t("connectModel.title")}
          </DialogTitle>
          <DialogDescription className="text-xs leading-5">
            {t("connectModel.description")}
          </DialogDescription>
        </DialogHeader>

        {catalogLoading && quickProviders.length === 0 ? (
          <div
            role="status"
            className="flex h-9 items-center text-xs text-muted-foreground"
          >
            {t("connectModel.loading")}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {quickProviders.map((template) => {
              const selected = selectedTemplateId === template.id
              return (
                <button
                  key={template.id}
                  type="button"
                  aria-pressed={selected}
                  className={cn(
                    "flex h-9 items-center justify-center gap-1.5 rounded-[6px] border px-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30",
                    selected
                      ? "border-foreground/25 bg-muted/65 text-foreground"
                      : "border-border/75 bg-background text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                  )}
                  onClick={() => {
                    setSelectedTemplateId(template.id)
                    setFailure(null)
                  }}
                >
                  <ProviderIcon provider={template.kind} className="size-3.5" />
                  <span className="truncate">{template.name}</span>
                </button>
              )
            })}
          </div>
        )}

        {catalogError ? (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 rounded-[6px] border border-[#E8D9A7] bg-[#FBF3DB] px-3 py-2 text-xs leading-5 text-[#7A5A10]"
          >
            <span>{t("connectModel.catalogError")}</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 shrink-0 px-2 text-xs text-[#7A5A10] hover:bg-[#E8D9A7]/40 hover:text-[#7A5A10]"
              onClick={() => void refreshCatalog()}
            >
              {t("connectModel.retry")}
            </Button>
          </div>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="connect-model-api-key" className="text-xs">
            {t("connectModel.apiKey")}
          </Label>
          <Input
            id="connect-model-api-key"
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder={t("connectModel.apiKeyPlaceholder")}
            className="h-9 rounded-[6px] shadow-none"
            onChange={(event) => {
              setApiKey(event.target.value)
              setFailure(null)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") void submit()
            }}
          />
        </div>

        {failureStage ? (
          <p
            role="alert"
            className="rounded-[6px] border border-[#F4D6D7] bg-[#FDEBEC] px-3 py-2 text-xs leading-5 text-[#9F2F2D]"
          >
            {t(`connectModel.errors.${failureStage}`)}
          </p>
        ) : null}

        <DialogFooter className="flex-row items-center justify-between sm:justify-between">
          <Button asChild variant="ghost" size="sm" className="h-8 px-2 text-xs">
            <Link href="/settings?section=providers">
              {t("connectModel.moreProviders")}
            </Link>
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-[6px] bg-[#111111] px-3 text-xs text-white shadow-none hover:bg-[#2F3437]"
            disabled={
              !selectedTemplateId || !apiKey.trim() || submitting || isConnecting
            }
            onClick={() => void submit()}
          >
            {submitting || isConnecting
              ? t("connectModel.connecting")
              : t("connectModel.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
