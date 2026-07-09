/**
 * Audit log action configuration
 *
 * Maps audit action strings to display labels, icons, and accent variants.
 * Used by RunAuditTab to render the timeline.
 */

import {
  Activity,
  AlertCircle,
  Ban,
  CheckCircle2,
  Clock,
  Pencil,
  Play,
  PlusCircle,
  RotateCw,
  Trash2,
  type AppIcon,
} from "@/lib/icons"
import type { StatusBadgeProps } from "@/components/ui/status-badge"

type AuditVariant = NonNullable<StatusBadgeProps["variant"]>

type AuditActionConfig = {
  labelKey: string
  variant: AuditVariant
  icon: AppIcon
}

export const auditActionConfig: Record<string, AuditActionConfig> = {
  "run.created": { labelKey: "created", variant: "info", icon: PlusCircle },
  "run.queued": { labelKey: "queued", variant: "warning", icon: Clock },
  "run.started": { labelKey: "started", variant: "running", icon: Play },
  "run.completed": { labelKey: "completed", variant: "success", icon: CheckCircle2 },
  "run.failed": { labelKey: "failed", variant: "destructive", icon: AlertCircle },
  "run.cancelled": { labelKey: "cancelled", variant: "neutral", icon: Ban },
  "run.retried": { labelKey: "retried", variant: "info", icon: RotateCw },
  "run.resumed": { labelKey: "resumed", variant: "info", icon: Play },
  "run.cleanup": { labelKey: "cleanup", variant: "neutral", icon: Trash2 },
  "run.timeout": { labelKey: "timeout", variant: "destructive", icon: AlertCircle },
}

export const DEFAULT_AUDIT_CONFIG: AuditActionConfig = {
  labelKey: "unknown",
  variant: "neutral",
  icon: Activity,
}

/**
 * Resolve the icon for any action slug — falls back via fuzzy match
 * (e.g. unknown "queued" string still maps to Clock).
 */
const ICON_FALLBACKS: Array<[RegExp, AppIcon]> = [
  [/queue/i, Clock],
  [/start|run|resume/i, Play],
  [/complete|finish|success|done/i, CheckCircle2],
  [/fail|error|timeout/i, AlertCircle],
  [/cancel|abort/i, Ban],
  [/retry/i, RotateCw],
  [/create|new/i, PlusCircle],
  [/update|edit|patch/i, Pencil],
  [/clean|delete|remove/i, Trash2],
]

export function auditActionIcon(action: string): AppIcon {
  const direct = auditActionConfig[action]
  if (direct) return direct.icon
  for (const [pattern, icon] of ICON_FALLBACKS) {
    if (pattern.test(action)) return icon
  }
  return DEFAULT_AUDIT_CONFIG.icon
}

const ACCENT_CLASS: Record<AuditVariant, string> = {
  success: "text-success bg-success-muted border-success-border",
  warning: "text-warning bg-warning-muted border-warning-border",
  info: "text-info bg-info-muted border-info-border",
  neutral: "text-muted-foreground bg-muted border-border",
  destructive: "text-error bg-error-muted border-error-border",
  running: "text-warning bg-warning-muted border-warning-border",
}

export function auditAccentClass(variant: AuditVariant): string {
  return ACCENT_CLASS[variant]
}
