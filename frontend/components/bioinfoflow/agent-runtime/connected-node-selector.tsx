"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { Check, ChevronDown, TerminalSquare } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  demoConnectionNodes,
  getDemoConnectionText,
  type DemoConnectionStatus,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

type ConnectedNodeSelectorProps = {
  disabled?: boolean
  compact?: boolean
}

const statusDotClassNames: Record<DemoConnectionStatus, string> = {
  online: "bg-emerald-500 shadow-emerald-500/40",
  offline: "bg-rose-500 shadow-rose-500/40",
  partial: "bg-amber-500 shadow-amber-500/40",
  unknown: "bg-slate-400 shadow-slate-400/30",
}

function StatusDot({ status }: { status: DemoConnectionStatus }) {
  return (
    <span
      className={cn("h-2.5 w-2.5 rounded-full shadow-[0_0_0_3px]", statusDotClassNames[status])}
      aria-hidden="true"
    />
  )
}

export function ConnectedNodeSelector({ disabled = false, compact = false }: ConnectedNodeSelectorProps) {
  const t = useTranslations("agentRuntime.connectedNode")
  const locale =
    typeof document === "undefined" ? "en" : document.documentElement.lang || navigator.language || "en"
  const [selectedNodeId, setSelectedNodeId] = useState(demoConnectionNodes[0]?.id ?? "")
  const selectedNode = useMemo(
    () => demoConnectionNodes.find((node) => node.id === selectedNodeId) ?? null,
    [selectedNodeId],
  )
  const selectedStatus = selectedNode ? t(`status.${selectedNode.status}`) : ""

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className={cn(
            "h-9 min-w-0 max-w-[12rem] rounded-full border border-border/70 bg-card px-2.5 text-xs font-medium text-muted-foreground shadow-xs hover:bg-muted/70 hover:text-foreground",
            compact && "max-w-[10rem]",
          )}
          disabled={disabled}
          aria-label={
            selectedNode
              ? t("selectedAria", { address: selectedNode.address, status: selectedStatus })
              : t("placeholder")
          }
        >
          <TerminalSquare className="h-3.5 w-3.5 shrink-0" />
          {selectedNode ? <StatusDot status={selectedNode.status} /> : null}
          <span className="min-w-0 truncate font-mono">
            {selectedNode ? selectedNode.address : t("placeholder")}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="top"
        sideOffset={10}
        className="w-80 rounded-2xl border-border/70 bg-popover p-1.5 shadow-2xl shadow-foreground/10"
      >
        <DropdownMenuLabel className="px-2.5 py-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
          {t("menuTitle")}
        </DropdownMenuLabel>
        {demoConnectionNodes.map((node) => {
          const selected = node.id === selectedNodeId
          const label = getDemoConnectionText(node.label, locale)
          const summary = [label, node.tags.join(" / ")].filter(Boolean).join(" · ")
          return (
            <DropdownMenuItem
              key={node.id}
              className="items-start gap-3 rounded-xl px-2.5 py-2.5 text-sm"
              onSelect={() => setSelectedNodeId(node.id)}
            >
              <StatusDot status={node.status} />
              <span className="min-w-0 flex-1">
                <span className="block font-mono font-medium text-foreground">{node.address}</span>
                <span className="mt-0.5 block truncate text-xs leading-5 text-muted-foreground">
                  {summary}
                </span>
              </span>
              {selected ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : null}
            </DropdownMenuItem>
          )
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="rounded-xl px-2.5 py-2 text-sm">
          <Link href="/connections">
            <TerminalSquare className="h-4 w-4" />
            <span>{t("manage")}</span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
