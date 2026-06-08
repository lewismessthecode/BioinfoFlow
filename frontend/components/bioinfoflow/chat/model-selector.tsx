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
import type { ProviderModels } from "@/hooks/use-llm-settings"
import { ProviderIcon } from "./provider-icons"

interface ModelSelectorProps {
  models: ProviderModels[]
  selectedModel: string
  onSelectModel: (model: string) => void
  disabled?: boolean
  allowAuto?: boolean
}

export function ModelSelector({
  models,
  selectedModel,
  onSelectModel,
  disabled = false,
  allowAuto = false,
}: ModelSelectorProps) {
  const t = useTranslations("settings.modelSelector")
  const [open, setOpen] = useState(false)

  // Find the display name for the current selection
  const currentModel = models
    .flatMap((pm) => pm.models.map((m) => ({ ...m, provider: pm.provider })))
    .find((m) => m.id === selectedModel)

  const displayLabel = currentModel?.name ?? (allowAuto ? t("auto") : t("noProviders"))

  if (models.length === 0) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="h-8 gap-1.5 rounded-full px-2.5 text-muted-foreground/80 hover:text-foreground hover:bg-secondary/70 text-xs font-medium transition-colors"
        disabled={disabled}
        aria-label={t("configure")}
        asChild
      >
        <Link href="/settings">
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
          className="h-8 max-w-[176px] gap-1.5 rounded-full px-2.5 text-muted-foreground/80 hover:text-foreground hover:bg-secondary/70 text-xs font-medium transition-colors"
          disabled={disabled}
          role="combobox"
          aria-expanded={open}
          aria-label={displayLabel}
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
        className="w-[260px] p-0 rounded-2xl overflow-hidden backdrop-blur-xl bg-background/95 border-black/5 dark:border-white/10 shadow-2xl"
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
                      onSelectModel("")
                      setOpen(false)
                    }}
                    className="flex items-center justify-between px-3 py-2"
                  >
                    <div className="flex items-center gap-2.5">
                      <SettingsIcon className="h-3.5 w-3.5 opacity-60" />
                      <span className="text-sm">{t("auto")}</span>
                    </div>
                    {selectedModel === "" ? (
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
                        onSelectModel(model.id)
                        setOpen(false)
                      }}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="flex items-center gap-2.5">
                        <ProviderIcon provider={providerGroup.provider} size={14} />
                        <span className="text-sm">{model.name}</span>
                      </div>
                      {selectedModel === model.id && (
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
                  window.location.href = "/settings"
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
