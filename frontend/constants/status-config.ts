/**
 * Status configuration for runs.
 *
 * `runStatusVariant` maps RunStatus → StatusBadge variant names.
 * This is the single source of truth for status→color mapping.
 *
 * `runStatusLabel` maps RunStatus → i18n translation keys (used with useTranslations("status")).
 */

import type { RunStatus } from "@/lib/types"
import type { StatusBadgeProps } from "@/components/ui/status-badge"

export const runStatusVariant: Record<RunStatus, NonNullable<StatusBadgeProps["variant"]>> = {
  pending: "neutral",
  completed: "success",
  running: "running",
  queued: "warning",
  failed: "destructive",
  cancelled: "neutral",
}

/** Translation keys for status labels — use with useTranslations("status") */
export const runStatusLabel: Record<RunStatus, string> = {
  pending: "pending",
  completed: "completed",
  running: "running",
  queued: "queued",
  failed: "failed",
  cancelled: "cancelled",
}
