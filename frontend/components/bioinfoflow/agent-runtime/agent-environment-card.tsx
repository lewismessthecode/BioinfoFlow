"use client"

import type React from "react"
import { CheckCircle2, Circle, GitBranch, GitCompare, Settings, Waypoints } from "@/lib/icons"
import { useTranslations } from "next-intl"

import {
  buildAgentRuntimeToolActivities,
  type AgentRuntimeArtifact,
  type AgentRuntimeEvent,
  type AgentRuntimeSession,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { todosFromArtifact } from "./artifact-viewers"
import { TodoChecklist } from "./todo-checklist"

type AgentEnvironmentCardProps = {
  projectId?: string | null
  session?: AgentRuntimeSession | null
  events: AgentRuntimeEvent[]
  artifacts: AgentRuntimeArtifact[]
}

export function AgentEnvironmentCard({
  projectId,
  session,
  events,
  artifacts,
}: AgentEnvironmentCardProps) {
  const t = useTranslations("agentRuntime")
  const changes = summarizeChanges(events, artifacts)
  const activities = buildAgentRuntimeToolActivities(events)
  const latestTodos = latestTodoArtifact(artifacts)
  const todos = latestTodos ? todosFromArtifact(latestTodos) : []
  const completedTodos = todos.filter((todo) => todo.status === "completed").length
  const progressLabel = todos.length
    ? t("environment.progressCount", { completed: completedTodos, total: todos.length })
    : t("environment.none")
  const sources = uniqueStrings([
    ...activities.flatMap((activity) => activity.relatedFiles),
    ...artifacts.flatMap((artifact) => artifactPaths(artifact)),
  ]).slice(0, 5)
  const remoteProjectRoot = remoteMetadataValue(session?.metadata, "remote_project_root")
  const remoteConnectionId = remoteMetadataValue(session?.metadata, "remote_connection_id")

  return (
    <section
      className="w-full max-w-[440px] rounded-[12px] border border-border/70 bg-card px-4 py-4 shadow-[0_10px_26px_rgba(36,35,33,0.06)]"
      data-testid="agent-environment-card"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-muted-foreground">
          {t("environment.title")}
        </h2>
        <Settings className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </div>

      <div className="grid gap-2.5">
        <EnvironmentRow
          icon={<GitCompare className="h-4 w-4" />}
          label={t("environment.changes")}
          value={changes.files ? t("environment.filesChanged", { count: changes.files }) : t("environment.none")}
          trailing={
            <div className="flex shrink-0 items-center gap-1 font-mono text-sm">
              <span className="text-emerald-600">+{changes.additions}</span>
              <span className="text-red-600">-{changes.deletions}</span>
            </div>
          }
        />
        <EnvironmentRow
          icon={<Waypoints className="h-4 w-4" />}
          label={t("environment.worktree")}
          value={projectId || t("environment.none")}
        />
        {remoteProjectRoot ? (
          <EnvironmentRow
            icon={<Waypoints className="h-4 w-4" />}
            label={t("environment.remoteProject")}
            value={remoteConnectionId ? `${remoteProjectRoot} · ${remoteConnectionId}` : remoteProjectRoot}
          />
        ) : null}
        <EnvironmentRow
          icon={<GitBranch className="h-4 w-4" />}
          label={t("environment.session")}
          value={session?.id ?? t("environment.pendingSession")}
        />
        <EnvironmentRow
          icon={<Circle className="h-4 w-4" />}
          label={t("environment.model")}
          value={modelLabel(session) ?? t("environment.none")}
        />
      </div>

      <div className="my-4 border-t border-border/60" />

      <section className="grid gap-2">
        <div className="text-sm font-semibold text-muted-foreground">
          {t("environment.progress")}
        </div>
        <div className="text-sm text-foreground">{progressLabel}</div>
        {todos.length ? <TodoChecklist todos={todos} compact /> : null}
      </section>

      <div className="my-4 border-t border-border/60" />

      <section className="grid gap-2">
        <div className="text-sm font-semibold text-muted-foreground">
          {t("environment.activity")}
        </div>
        {activities.length ? (
          <div className="grid gap-1.5">
            {activities.slice(-4).map((activity) => (
              <div
                key={activity.id}
                className="flex min-w-0 items-center gap-2 text-sm"
                title={activity.summary || activity.name}
              >
                <CheckCircle2 className={cn(
                  "h-4 w-4 shrink-0",
                  activity.status === "completed"
                    ? "text-emerald-500"
                    : "text-muted-foreground",
                )} />
                <span className="min-w-0 flex-1 truncate">{activity.summary || activity.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t(`activity.status.${activity.status}`)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">{t("environment.none")}</div>
        )}
      </section>

      <div className="my-4 border-t border-border/60" />

      <section className="grid gap-2">
        <div className="text-sm font-semibold text-muted-foreground">
          {t("environment.sources")}
        </div>
        {sources.length ? (
          <div className="flex flex-wrap gap-2">
            {sources.map((source) => (
              <span
                key={source}
                className="max-w-full truncate rounded-[6px] border border-border/60 px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                title={source}
              >
                {source}
              </span>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">{t("environment.none")}</div>
        )}
      </section>
    </section>
  )
}

function EnvironmentRow({
  icon,
  label,
  value,
  trailing,
}: {
  icon: React.ReactNode
  label: string
  value: string
  trailing?: React.ReactNode
}) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="truncate text-xs text-muted-foreground" title={value}>
          {value}
        </div>
      </div>
      {trailing}
    </div>
  )
}

function summarizeChanges(
  events: AgentRuntimeEvent[],
  artifacts: AgentRuntimeArtifact[],
) {
  const records = [
    ...events.flatMap((event) => nestedRecords(event.payload)),
    ...artifacts.flatMap((artifact) => nestedRecords(artifact.payload ?? {})),
  ]
  const files = uniqueStrings(records.flatMap(pathsFromRecord)).length
  const additions = sumRecordNumbers(records, ["additions", "added", "insertions", "lines_added"])
  const deletions = sumRecordNumbers(records, ["deletions", "deleted", "removals", "lines_deleted"])
  return { files, additions, deletions }
}

function nestedRecords(value: unknown): Record<string, unknown>[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return []
  const record = value as Record<string, unknown>
  return [
    record,
    ...Object.values(record).flatMap((entry) => nestedRecords(entry)),
  ]
}

function pathsFromRecord(record: Record<string, unknown>) {
  const values: string[] = []
  for (const key of ["path", "file_path", "filename", "target", "source"]) {
    const value = record[key]
    if (typeof value === "string" && looksPathLike(value)) values.push(value)
  }
  for (const key of ["files", "changed_files", "paths"]) {
    const value = record[key]
    if (Array.isArray(value)) {
      values.push(...value.filter((entry): entry is string => typeof entry === "string"))
    }
  }
  return values
}

function artifactPaths(artifact: AgentRuntimeArtifact) {
  return uniqueStrings([
    artifact.file_path,
    typeof artifact.payload?.path === "string" ? artifact.payload.path : null,
  ])
}

function sumRecordNumbers(records: Record<string, unknown>[], keys: string[]) {
  return records.reduce((sum, record) => {
    for (const key of keys) {
      const value = record[key]
      if (typeof value === "number" && Number.isFinite(value)) return sum + value
    }
    return sum
  }, 0)
}

function latestTodoArtifact(artifacts: AgentRuntimeArtifact[]) {
  return [...artifacts]
    .filter((artifact) => artifact.type === "todo_list")
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0]
}

function modelLabel(session?: AgentRuntimeSession | null) {
  const selection = session?.model_selection
  if (!selection?.model) return null
  return [selection.provider, selection.model].filter(Boolean).join(" · ")
}

function remoteMetadataValue(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
) {
  const value = metadata?.[key]
  return typeof value === "string" && value ? value : null
}

function uniqueStrings(values: Array<string | null | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))]
}

function looksPathLike(value: string) {
  return value.includes("/") || value.startsWith(".") || /\.[A-Za-z0-9]{1,8}$/.test(value)
}
