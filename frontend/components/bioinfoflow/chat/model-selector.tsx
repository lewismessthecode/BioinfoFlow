"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import {
  Check,
  ChevronDown,
  Settings as SettingsIcon,
  Sparkles,
} from "@/lib/icons"
import Link from "next/link"
import {
  composerSelectorChevronClassName,
  composerSelectorMenuItemClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import {
  ComposerSelectorChevronSlot,
  ComposerSelectorIconSlot,
  ComposerSelectorMenuSurface,
  ComposerSelectorText,
  ComposerSelectorTrigger,
} from "@/components/bioinfoflow/composer-selector"
import { Popover, PopoverTrigger } from "@/components/ui/popover"
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
    ? compact
      ? "max-w-9 px-2"
      : "max-w-[168px]"
    : "h-9 max-w-[196px] gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"
  const configureClassName = isComposer
    ? compact
      ? "max-w-9 px-2"
      : "max-w-[168px]"
    : "h-9 gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium text-muted-foreground/80 shadow-lg shadow-foreground/5 backdrop-blur transition-colors hover:bg-background hover:text-foreground"

  // Find the display name for the current selection
  const currentModel = models
    .flatMap((pm) =>
        pm.models.map((m) => ({
          ...m,
          provider: pm.provider,
          providerKind: pm.provider_kind,
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
      <ComposerSelectorTrigger
        presentation={variant}
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
          <ComposerSelectorIconSlot presentation={variant}>
            <SettingsIcon className={isComposer ? undefined : "h-3.5 w-3.5"} />
          </ComposerSelectorIconSlot>
          <ComposerSelectorText
            presentation={variant}
            className={cn(compact ? "sr-only" : "hidden sm:inline")}
          >
            {t("configure")}
          </ComposerSelectorText>
        </Link>
      </ComposerSelectorTrigger>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <ComposerSelectorTrigger
          presentation={variant}
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
          <ComposerSelectorIconSlot presentation={variant}>
            {currentModel ? (
              <ProviderIcon
                provider={currentModel.providerKind}
                providerLabel={currentModel.label}
                baseUrl={currentModel.baseUrl}
                modelId={currentModel.id}
                modelName={currentModel.name}
                size={13}
              />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
          </ComposerSelectorIconSlot>
          <ComposerSelectorText
            presentation={variant}
            className={cn(compact ? "sr-only" : "hidden sm:inline")}
          >
            {displayLabel}
          </ComposerSelectorText>
          <ComposerSelectorChevronSlot
            presentation={variant}
            className={cn(compact && "hidden")}
          >
            <ChevronDown
              className={
                isComposer
                  ? composerSelectorChevronClassName
                  : "h-3 w-3 shrink-0 opacity-50"
              }
            />
          </ComposerSelectorChevronSlot>
        </ComposerSelectorTrigger>
      </PopoverTrigger>
      <ComposerSelectorMenuSurface
        kind="popover"
        presentation={variant}
        align="start"
        side="top"
        className={cn(
          isComposer ? "w-[244px] overflow-hidden" : "w-[280px] overflow-hidden p-0",
          !isComposer &&
            "rounded-xl border border-border/70 bg-background/96 shadow-[0_14px_34px_rgba(15,15,15,0.06)]",
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
                      isComposer ? composerSelectorMenuItemClassName : "px-3 py-2",
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
                      keywords={[
                        providerGroup.label,
                        providerGroup.provider_kind,
                        model.id,
                      ]}
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
                        isComposer ? composerSelectorMenuItemClassName : "px-3 py-2",
                      )}
                    >
                      <div className={cn("flex items-center", isComposer ? "gap-2" : "gap-2.5")}>
                        <ProviderIcon
                          provider={providerGroup.provider_kind}
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
                className={cn(
                  isComposer ? composerSelectorMenuItemClassName : "px-3 py-2",
                )}
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
      </ComposerSelectorMenuSurface>
    </Popover>
  )
}
