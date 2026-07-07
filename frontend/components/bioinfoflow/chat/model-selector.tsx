"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { Check, ChevronDown, Settings as SettingsIcon } from "lucide-react"
import Link from "next/link"
import {
  composerSelectorChevronClassName,
  composerSelectorChipClassName,
  composerSelectorIconClassName,
  composerSelectorMenuClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
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
import { cn } from "@/lib/utils"
import { ProviderIcon } from "./provider-icons"

interface ModelSelectorProps {
  models: ProviderModels[]
  selectedModel: ModelSelection | null
  onSelectModel: (selection: ModelSelection | null) => void
  disabled?: boolean
  allowAuto?: boolean
  variant?: "default" | "composer"
  compact?: boolean
}

export function ModelSelector({
  models,
  selectedModel,
  onSelectModel,
  disabled = false,
  allowAuto = false,
  variant = "default",
  compact = false,
}: ModelSelectorProps) {
  const t = useTranslations("settings.modelSelector")
  const [open, setOpen] = useState(false)
  const isComposer = variant === "composer"
  const triggerClassName = isComposer
    ? cn(composerSelectorChipClassName, compact ? "max-w-9 px-2" : "max-w-[168px]")
    : "h-9 max-w-[196px] gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"
  const configureClassName = isComposer
    ? cn(composerSelectorChipClassName, compact ? "max-w-9 px-2" : "max-w-[168px]")
    : "h-9 gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"

  // Find the display name for the current selection
  const currentModel = models
    .flatMap((pm) =>
        pm.models.map((m) => ({
          ...m,
          provider: pm.provider,
          label: pm.label,
          baseUrl: pm.base_url,
        })),
    )
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
        data-composer-chip={isComposer ? "true" : undefined}
        asChild
      >
        <Link href="/settings?section=providers">
          <SettingsIcon
            className={isComposer ? composerSelectorIconClassName : "h-3.5 w-3.5"}
          />
          <span className={cn(compact ? "sr-only" : "hidden sm:inline")}>{t("configure")}</span>
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
          data-composer-chip={isComposer ? "true" : undefined}
        >
          {currentModel && (
            <ProviderIcon
              provider={currentModel.provider}
              providerLabel={currentModel.label}
              baseUrl={currentModel.baseUrl}
              modelId={currentModel.id}
              modelName={currentModel.name}
              size={13}
            />
          )}
          <span className={cn("truncate", compact ? "sr-only" : "hidden sm:inline")}>
            {displayLabel}
          </span>
          <ChevronDown
            className={cn(
              isComposer
                ? composerSelectorChevronClassName
                : "h-3 w-3 shrink-0 opacity-50",
              compact && "hidden",
            )}
          />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        className={cn(
          isComposer ? "w-[244px] overflow-hidden" : "w-[280px] overflow-hidden p-0",
          isComposer
            ? composerSelectorMenuClassName
            : "rounded-xl border border-border/70 bg-background/96 shadow-[0_14px_34px_rgba(15,15,15,0.06)]",
        )}
      >
        <Command>
          <CommandInput placeholder={t("searchModels")} className={isComposer ? "h-7 text-[12px]" : "h-9"} />
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
                    className={cn(
                      "flex items-center justify-between",
                      isComposer ? "min-h-7 px-2 py-1.5 text-xs" : "px-3 py-2",
                    )}
                  >
                    <div className={cn("flex items-center", isComposer ? "gap-2" : "gap-2.5")}>
                      <SettingsIcon className={cn(isComposer ? "h-3 w-3" : "h-3.5 w-3.5", "opacity-60")} />
                      <span className={isComposer ? "text-xs" : "text-sm"}>{t("auto")}</span>
                    </div>
                    {selectedModel === null ? (
                      <Check className={cn(isComposer ? "h-3 w-3" : "h-3.5 w-3.5", "text-primary")} />
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
                      className={cn(
                        "flex items-center justify-between",
                        isComposer ? "min-h-7 px-2 py-1.5 text-xs" : "px-3 py-2",
                      )}
                    >
                      <div className={cn("flex items-center", isComposer ? "gap-2" : "gap-2.5")}>
                        <ProviderIcon
                          provider={providerGroup.provider}
                          providerLabel={providerGroup.label}
                          baseUrl={providerGroup.base_url}
                          modelId={model.id}
                          modelName={model.name}
                          size={isComposer ? 13 : 14}
                        />
                        <span className={isComposer ? "text-xs" : "text-sm"}>{model.name}</span>
                      </div>
                      {selectedModel?.provider === providerGroup.provider &&
                      selectedModel?.model === model.id && (
                        <Check className={cn(isComposer ? "h-3 w-3" : "h-3.5 w-3.5", "text-primary")} />
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </div>
            ))}
            <CommandSeparator />
            <CommandGroup>
              <CommandItem
                value={t("configure")}
                asChild
                className={cn(isComposer ? "px-2 py-1.5" : "px-3 py-2")}
              >
                <Link href="/settings?section=providers" onClick={() => setOpen(false)}>
                  <SettingsIcon className={cn(isComposer ? "h-3 w-3" : "h-3.5 w-3.5", "mr-2 opacity-50")} />
                  <span className="text-xs text-muted-foreground">
                    {t("configure")}
                  </span>
                </Link>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
