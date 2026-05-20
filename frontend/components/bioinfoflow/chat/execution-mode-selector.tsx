"use client"

import { useCallback, useMemo } from "react"
import { Check, ShieldCheck, ShieldAlert, Zap } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { ExecutionPolicy } from "@/lib/types"

/**
 * ExecutionModeSelector — lets the user switch a conversation between
 * "Ask" (default, prompt on ACT_HIGH), "Auto approve" (prompt on ACT_LOW
 * and ACT_HIGH — stricter), and "Bypass" (never prompt, like Claude Code's
 * dangerously-skip-permissions). State is persisted server-side so the
 * backend's agent loop knows which policy to apply.
 */
interface ExecutionModeSelectorProps {
  value: ExecutionPolicy | null
  onChange: (next: ExecutionPolicy) => void | Promise<void>
  disabled?: boolean
}

export function ExecutionModeSelector({
  value,
  onChange,
  disabled,
}: ExecutionModeSelectorProps) {
  const t = useTranslations("executionMode")

  // null (unset) falls back to the server-side default, which is `auto`.
  const active: ExecutionPolicy = value ?? "auto"

  const handleSelect = useCallback(
    async (next: ExecutionPolicy) => {
      if (next === active) return
      try {
        await onChange(next)
      } catch {
        toast.error(t("changeFailed"))
      }
    },
    [active, onChange, t],
  )

  const trigger = useMemo(() => {
    if (active === "bypass") {
      return {
        icon: <Zap className="h-3.5 w-3.5" aria-hidden />,
        label: t("bypassShort"),
        cls: "text-amber-600 dark:text-amber-400",
      }
    }
    if (active === "approve_all") {
      return {
        icon: <ShieldAlert className="h-3.5 w-3.5" aria-hidden />,
        label: t("approveAllShort"),
        cls: "text-foreground",
      }
    }
    return {
        icon: <ShieldCheck className="h-3.5 w-3.5" aria-hidden />,
      label: t("askShort"),
      cls: "text-muted-foreground",
    }
  }, [active, t])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          className={cn(
            "h-8 gap-1.5 rounded-full px-2.5 text-xs font-medium hover:bg-secondary/70",
            trigger.cls,
          )}
          disabled={disabled}
          aria-label={t("triggerAriaLabel")}
        >
          {trigger.icon}
          <span className="hidden sm:inline">{trigger.label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64 rounded-2xl">
        <DropdownMenuLabel>{t("menuLabel")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <ModeItem
          icon={<ShieldCheck className="h-4 w-4" />}
          title={t("askTitle")}
          description={t("askDescription")}
          active={active === "auto"}
          onSelect={() => handleSelect("auto")}
        />
        <ModeItem
          icon={<ShieldAlert className="h-4 w-4" />}
          title={t("approveAllTitle")}
          description={t("approveAllDescription")}
          active={active === "approve_all"}
          onSelect={() => handleSelect("approve_all")}
        />
        <ModeItem
          icon={<Zap className="h-4 w-4 text-amber-500" />}
          title={t("bypassTitle")}
          description={t("bypassDescription")}
          active={active === "bypass"}
          onSelect={() => handleSelect("bypass")}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface ModeItemProps {
  icon: React.ReactNode
  title: string
  description: string
  active: boolean
  onSelect: () => void
}

function ModeItem({ icon, title, description, active, onSelect }: ModeItemProps) {
  return (
    <DropdownMenuItem
      onClick={onSelect}
      className="gap-3 py-2 cursor-pointer rounded-xl"
    >
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center">
        {icon}
      </div>
      <div className="flex-1 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{title}</span>
          {active && (
            <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden />
          )}
        </div>
        <p className="text-xs text-muted-foreground leading-snug">
          {description}
        </p>
      </div>
    </DropdownMenuItem>
  )
}
