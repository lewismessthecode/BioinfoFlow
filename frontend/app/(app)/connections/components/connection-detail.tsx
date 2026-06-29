"use client"

import { Pencil, Play, Plus, RefreshCw, Server, TerminalSquare } from "lucide-react"
import { useTranslations } from "next-intl"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { RemoteConnection } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

import {
  DetailGrid,
  DetailItem,
  DetailSection,
  StatusDot,
  TextPanel,
  statusBorderClassNames,
} from "./connection-ui"

type ConnectionDetailProps = {
  connection: RemoteConnection | null
  hasConnections: boolean
  testing: boolean
  probing: boolean
  probeOutput: string
  onCreate: () => void
  onClearSearch: () => void
  onEdit: (connection: RemoteConnection) => void
  onTest: (connection: RemoteConnection) => void
  onRunProbe: (connection: RemoteConnection) => void
}

export function ConnectionDetail({
  connection,
  hasConnections,
  testing,
  probing,
  probeOutput,
  onCreate,
  onClearSearch,
  onEdit,
  onTest,
  onRunProbe,
}: ConnectionDetailProps) {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")

  if (!connection) {
    return (
      <section className="flex min-h-[280px] items-center justify-center p-6">
        <div className="max-w-md text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-2xl border border-border/60 bg-background/70 text-muted-foreground">
            <TerminalSquare className="h-5 w-5" />
          </div>
          <h2 className="mt-4 text-base font-semibold text-foreground">
            {hasConnections ? t("list.noResults") : t("emptyDetail.title")}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {hasConnections ? t("emptyDetail.searchDescription") : t("emptyDetail.description")}
          </p>
          <Button
            type="button"
            className="mt-4 rounded-full"
            variant={hasConnections ? "outline" : "default"}
            onClick={hasConnections ? onClearSearch : onCreate}
          >
            {hasConnections ? null : <Plus className="h-4 w-4" />}
            {hasConnections ? tCommon("clear") : t("emptyDetail.action")}
          </Button>
        </div>
      </section>
    )
  }

  return (
    <section className="min-w-0">
      <div className="border-b border-border/60 p-5">
        <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-border/60 bg-background/85 text-foreground">
              <Server className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-base font-semibold tracking-tight text-foreground">
                  {connection.name}
                </h2>
                <Badge
                  variant="outline"
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-xs",
                    statusBorderClassNames[connection.status],
                  )}
                >
                  <StatusDot status={connection.status} className="h-2 w-2 shadow-none" />
                  {t(`status.${connection.status}`)}
                </Badge>
              </div>
              <p className="mt-0.5 font-mono text-sm text-muted-foreground">
                {connection.username}@{connection.host}:{connection.port}
              </p>
            </div>
          </div>
          <div className="flex w-fit flex-wrap gap-1 rounded-full border border-border/60 bg-muted/15 p-1 2xl:justify-end">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3 text-muted-foreground hover:bg-background/70 hover:text-foreground"
              onClick={() => onTest(connection)}
              disabled={testing}
            >
              <RefreshCw className={cn("h-4 w-4", testing && "animate-spin")} />
              {testing ? t("actions.testing") : t("actions.testConnection")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3 text-muted-foreground hover:bg-background/70 hover:text-foreground"
              onClick={() => onEdit(connection)}
            >
              <Pencil className="h-4 w-4" />
              {t("actions.editConnection")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3 text-muted-foreground hover:bg-background/70 hover:text-foreground"
              onClick={() => onRunProbe(connection)}
              disabled={probing}
            >
              <Play className="h-4 w-4" />
              {probing ? t("actions.runningProbe") : t("actions.runProbe")}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:p-5">
        <DetailSection title={t("detail.overview")}>
          <DetailGrid>
            <DetailItem label={t("fields.name")} value={connection.name} />
            <DetailItem
              label={t("fields.host")}
              value={`${connection.username}@${connection.host}:${connection.port}`}
              mono
            />
          </DetailGrid>
        </DetailSection>

        <DetailSection title={t("detail.health")}>
          <DetailGrid>
            <DetailItem label={t("fields.status")} value={t(`status.${connection.status}`)} />
            <DetailItem label={t("fields.auth")} value={t(`auth.${connection.auth_method}`)} />
          </DetailGrid>
          {connection.status_message ? (
            <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {connection.status_message}
            </div>
          ) : connection.status === "unknown" ? (
            <p className="text-sm leading-6 text-muted-foreground">{t("detail.notTested")}</p>
          ) : null}
        </DetailSection>

        <DetailSection title={t("detail.access")}>
          <DetailGrid>
            <DetailItem label={t("fields.port")} value={String(connection.port)} mono />
            <DetailItem label={t("fields.username")} value={connection.username} mono />
            {connection.auth_method === "ssh_config" ? (
              <DetailItem label={t("fields.sshAlias")} value={connection.ssh_alias || t("empty.notSet")} mono />
            ) : null}
            {connection.auth_method === "key_file" ? (
              <DetailItem label={t("fields.keyPath")} value={connection.key_path || t("empty.notSet")} mono />
            ) : null}
          </DetailGrid>
        </DetailSection>

        <DetailSection title={t("detail.agentUse")}>
          <p className="text-sm leading-6 text-muted-foreground">{t("detail.skillGuidance")}</p>
          <TextPanel
            title={t("fields.skillInstructions")}
            value={connection.skill_instructions}
            empty={t("detail.noInstructions")}
          />
        </DetailSection>

        {probeOutput || probing ? (
          <DetailSection title={t("probe.title")}>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <TerminalSquare className="h-4 w-4" />
              <span>{t("probe.description")}</span>
            </div>
            <pre className="min-h-12 whitespace-pre-wrap break-words rounded-xl bg-background/80 p-3 font-mono text-xs leading-5 text-foreground">
              {probeOutput || t("probe.placeholder")}
            </pre>
          </DetailSection>
        ) : null}
      </div>
    </section>
  )
}
