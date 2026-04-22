"use client"

import { useCallback, useEffect, useState } from "react"
import { Trash2, Plus, Bell } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { apiRequest, ApiError } from "@/lib/api"
import type { NotificationConfig, NotificationTrigger } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { StatusBadge } from "@/components/ui/status-badge"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface NotificationConfigPanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string | null
}

const TRIGGERS: NotificationTrigger[] = [
  "run.completed",
  "run.failed",
  "run.cancelled",
  "batch.completed",
  "batch.failed",
]

export function NotificationConfigPanel({
  open,
  onOpenChange,
  projectId,
}: NotificationConfigPanelProps) {
  const t = useTranslations("notificationConfig")
  const [configs, setConfigs] = useState<NotificationConfig[]>([])
  const [isLoading, setIsLoading] = useState(false)

  // Add form state
  const [showAddForm, setShowAddForm] = useState(false)
  const [newTrigger, setNewTrigger] = useState<NotificationTrigger>("run.completed")
  const [newWebhookUrl, setNewWebhookUrl] = useState("")
  const [newEnabled, setNewEnabled] = useState(true)
  const [isCreating, setIsCreating] = useState(false)

  const loadConfigs = useCallback(async () => {
    if (!projectId) return
    setIsLoading(true)
    try {
      const { data } = await apiRequest<NotificationConfig[]>(
        "/notifications",
        { params: { project_id: projectId } },
      )
      setConfigs(data)
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : t("errors.loadFailed")
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }, [projectId, t])

  useEffect(() => {
    if (open) {
      loadConfigs()
      setShowAddForm(false)
    }
  }, [open, loadConfigs])

  const handleCreate = async () => {
    if (!projectId || !newWebhookUrl.trim()) return
    setIsCreating(true)
    try {
      await apiRequest("/notifications", {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          trigger: newTrigger,
          webhook_url: newWebhookUrl.trim(),
          enabled: newEnabled,
        }),
      })
      toast.success(t("toasts.created"))
      setShowAddForm(false)
      setNewWebhookUrl("")
      setNewEnabled(true)
      loadConfigs()
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : t("errors.createFailed")
      toast.error(message)
    } finally {
      setIsCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await apiRequest(`/notifications/${id}`, { method: "DELETE" })
      toast.success(t("toasts.deleted"))
      setConfigs((prev) => prev.filter((c) => c.id !== id))
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : t("errors.deleteFailed")
      toast.error(message)
    }
  }

  const triggerVariant = (trigger: NotificationTrigger) => {
    if (trigger.includes("completed")) return "success" as const
    if (trigger.includes("failed")) return "destructive" as const
    return "neutral" as const
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{t("title")}</SheetTitle>
          <SheetDescription>{t("description")}</SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* Existing configs */}
          {isLoading ? (
            <p className="text-sm text-muted-foreground">{t("title")}...</p>
          ) : configs.length === 0 && !showAddForm ? (
            <EmptyState
              icon={Bell}
              title={t("empty")}
              description={t("emptyDescription")}
              className="py-8"
            />
          ) : (
            <div className="space-y-2">
              {configs.map((config) => (
                <div
                  key={config.id}
                  className="flex items-center gap-3 rounded-lg border border-border p-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusBadge variant={triggerVariant(config.trigger)}>
                        {t(`triggers.${config.trigger}`)}
                      </StatusBadge>
                      {!config.enabled && (
                        <span className="text-2xs text-muted-foreground uppercase">
                          disabled
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground font-mono truncate">
                      {config.webhook_url}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive shrink-0"
                    onClick={() => handleDelete(config.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          {/* Add form */}
          {showAddForm ? (
            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="space-y-2">
                <Label>{t("trigger")}</Label>
                <Select
                  value={newTrigger}
                  onValueChange={(v) =>
                    setNewTrigger(v as NotificationTrigger)
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRIGGERS.map((tr) => (
                      <SelectItem key={tr} value={tr}>
                        {t(`triggers.${tr}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>{t("webhookUrl")}</Label>
                <Input
                  value={newWebhookUrl}
                  onChange={(e) => setNewWebhookUrl(e.target.value)}
                  placeholder={t("webhookUrlPlaceholder")}
                  className="font-mono text-xs"
                />
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  checked={newEnabled}
                  onCheckedChange={setNewEnabled}
                />
                <Label>{t("enabled")}</Label>
              </div>

              <div className="flex gap-2 pt-1">
                <Button
                  size="sm"
                  onClick={handleCreate}
                  disabled={!newWebhookUrl.trim() || isCreating}
                >
                  {t("add")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowAddForm(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowAddForm(true)}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              {t("add")}
            </Button>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
