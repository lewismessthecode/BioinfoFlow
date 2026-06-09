"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { Check, ChevronDown, Settings as SettingsIcon } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import type { ModelSelection, ProviderModels } from "@/hooks/use-llm-settings"
import { ProviderIcon } from "./provider-icons"

interface ModelSelectorProps {
  models: ProviderModels[]
  selectedModel: ModelSelection | null
  onSelectModel: (selection: ModelSelection | null) => void
  disabled?: boolean
  allowAuto?: boolean
  variant?: "default" | "composer"
}

export function ModelSelector({
  models,
  selectedModel,
  onSelectModel,
  disabled = false,
  allowAuto = false,
  variant = "default",
}: ModelSelectorProps) {
  const t = useTranslations("settings.modelSelector")
  const [open, setOpen] = useState(false)
  const isComposer = variant === "composer"
  const triggerClassName = isComposer
    ? "h-9 max-w-[196px] gap-1 rounded-full px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground"
    : "h-9 max-w-[196px] gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"
  const configureClassName = isComposer
    ? "h-9 gap-1 rounded-full px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground"
    : "h-9 gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"

  // Find the display name for the current selection
  const currentModel = models
    .flatMap((pm) => pm.models.map((m) => ({ ...m, provider: pm.provider })))
    .find(
      (m) =>
        m.id === selectedModel?.model &&
        m.provider === selectedModel?.provider,
    )

  const displayLabel = currentModel?.name ?? (allowAuto ? t("auto") : t("noProviders"))

  if (models.length === 0) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className={configureClassName}
        disabled={disabled}
        aria-label={t("configure")}
        data-variant={variant}
        asChild
      >
        <Link href="/settings?section=providers">
          <SettingsIcon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{t("configure")}</span>
        </Link>
      </Button>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={triggerClassName}
          disabled={disabled}
          role="combobox"
          aria-expanded={open}
          aria-label={displayLabel}
          data-variant={variant}
        >
          {currentModel && (
            <ProviderIcon provider={currentModel.provider} size={13} />
          )}
          <span className="hidden truncate sm:inline">{displayLabel}</span>
          <ChevronDown className="h-3 w-3 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        className="w-[280px] overflow-hidden rounded-[22px] border border-border/70 bg-background/96 p-0 shadow-2xl shadow-foreground/10 backdrop-blur-xl"
      >
        <Command>
          <CommandInput placeholder={t("searchModels")} className="h-9" />
          <CommandList>
            <CommandEmpty>{t("noProviders")}</CommandEmpty>
            {allowAuto ? (
              <>
                <CommandGroup heading={t("section")}>
                  <CommandItem
                    value={t("auto")}
                      onSelect={() => {
                        onSelectModel(null)
                        setOpen(false)
                      }}
                    className="flex items-center justify-between px-3 py-2"
                  >
                    <div className="flex items-center gap-2.5">
                      <SettingsIcon className="h-3.5 w-3.5 opacity-60" />
                      <span className="text-sm">{t("auto")}</span>
                    </div>
                    {selectedModel === null ? (
                      <Check className="h-3.5 w-3.5 text-primary" />
                    ) : null}
                  </CommandItem>
                </CommandGroup>
                <CommandSeparator />
              </>
            ) : null}
            {models.map((providerGroup, index) => (
              <div key={providerGroup.provider}>
                {index > 0 && <CommandSeparator />}
                <CommandGroup
                  heading={providerGroup.label || providerGroup.provider}
                >
                  {providerGroup.models.map((model) => (
                    <CommandItem
                      key={model.id}
                      value={`${providerGroup.provider} ${model.name}`}
                      onSelect={() => {
                        onSelectModel({
                          provider: providerGroup.provider,
                          model: model.id,
                          model_id: model.model_id,
                        })
                        setOpen(false)
                      }}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="flex items-center gap-2.5">
                        <ProviderIcon provider={providerGroup.provider} size={14} />
                        <span className="text-sm">{model.name}</span>
                      </div>
                      {selectedModel?.provider === providerGroup.provider &&
                      selectedModel?.model === model.id && (
                        <Check className="h-3.5 w-3.5 text-primary" />
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </div>
            ))}
            <CommandSeparator />
            <CommandGroup>
              <CommandItem
                onSelect={() => {
                  setOpen(false)
                  window.location.href = "/settings?section=providers"
                }}
                className="px-3 py-2"
              >
                <SettingsIcon className="h-3.5 w-3.5 mr-2 opacity-50" />
                <span className="text-xs text-muted-foreground">
                  {t("configure")}
                </span>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
