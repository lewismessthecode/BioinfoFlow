"use client"

import { useState, useMemo } from "react"
import { Search, Check, Clock } from "@/lib/icons"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { useTranslations } from "next-intl"
import { engineStyleFor } from "../workflow-pills"
import type { Workflow } from "@/lib/types"

interface StepWorkflowSelectProps {
  workflows: Workflow[]
  selectedWorkflow: Workflow | null
  onSelect: (workflow: Workflow) => void
}

export function StepWorkflowSelect({
  workflows,
  selectedWorkflow,
  onSelect,
}: StepWorkflowSelectProps) {
  const t = useTranslations("workflows.submission")
  const [search, setSearch] = useState("")

  const filtered = useMemo(() => {
    const sorted = [...workflows].sort((a, b) => {
      const aTime = a.updated_at ? Date.parse(a.updated_at) : 0
      const bTime = b.updated_at ? Date.parse(b.updated_at) : 0
      if (bTime !== aTime) return bTime - aTime
      return a.name.localeCompare(b.name)
    })
    if (!search.trim()) return sorted
    const q = search.toLowerCase()
    return sorted.filter(
      (w) =>
        w.name.toLowerCase().includes(q) ||
        w.description?.toLowerCase().includes(q) ||
        w.engine.toLowerCase().includes(q),
    )
  }, [workflows, search])

  return (
    <section className="relative overflow-hidden rounded-2xl border border-border/60 bg-background p-4 shadow-sm dark:bg-card">
      <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-foreground/10 to-transparent" />
      <div className="space-y-3">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("step1.searchPlaceholder")}
          className="pl-8 h-9 text-xs rounded-xl border-border/70 bg-muted/15"
        />
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {filtered.map((w) => {
          const isSelected = selectedWorkflow?.id === w.id
          const engine = engineStyleFor(w.engine)
          return (
            <button
              key={w.id}
              type="button"
              aria-label={w.name}
              className={cn(
                "group relative text-left rounded-xl border p-3 transition-all duration-150",
                "bg-gradient-to-br from-muted/35 via-background to-background hover:border-foreground/15 hover:shadow-sm hover:-translate-y-px",
                isSelected
                  ? "border-primary/40 bg-primary/5 ring-1 ring-primary/20"
                  : "border-border/60",
              )}
              onClick={() => onSelect(w)}
            >
              {isSelected && (
                <div className="absolute top-2 right-2 w-4 h-4 rounded-full bg-primary text-primary-foreground flex items-center justify-center">
                  <Check className="h-2.5 w-2.5" />
                </div>
              )}
              <div className="text-sm font-semibold leading-tight truncate pr-5">{w.name}</div>
              {w.description && (
                <div className="text-xs-tight text-muted-foreground mt-1 line-clamp-2 leading-snug">
                  {w.description}
                </div>
              )}
              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                <span className={`text-2xs font-medium px-1.5 py-px rounded border ${engine.classes}`}>
                  {engine.label}
                </span>
                {w.estimated_time && (
                  <span className="flex items-center gap-0.5 text-2xs text-muted-foreground">
                    <Clock className="h-2.5 w-2.5" />
                    {w.estimated_time}
                  </span>
                )}
              </div>
            </button>
          )
        })}

        {filtered.length === 0 && (
          <div className="col-span-full py-8 text-center text-xs text-muted-foreground">
            {t("step1.noResults")}
          </div>
        )}
      </div>
      </div>
    </section>
  )
}
