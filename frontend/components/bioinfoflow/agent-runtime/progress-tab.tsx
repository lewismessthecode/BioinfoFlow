"use client"

import { useMemo, useState } from "react"
import { ChevronLeft } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"
import {
  ArtifactIcon,
  ArtifactViewer,
  artifactTypeLabel,
  todosFromArtifact,
} from "./artifact-viewers"
import { TodoChecklist } from "./todo-checklist"

export function ProgressTab({ artifacts }: { artifacts: AgentRuntimeArtifact[] }) {
  const t = useTranslations("agentRuntime")
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // The newest todo_list artifact is the live checklist; the latest call wins.
  const latestTodoArtifact = useMemo(() => {
    return [...artifacts]
      .filter((artifact) => artifact.type === "todo_list")
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0]
  }, [artifacts])

  const otherArtifacts = useMemo(
    () =>
      artifacts.filter(
        (artifact) => artifact.id !== latestTodoArtifact?.id,
      ),
    [artifacts, latestTodoArtifact],
  )

  const selected = useMemo(
    () => artifacts.find((artifact) => artifact.id === selectedId) ?? null,
    [artifacts, selectedId],
  )

  if (selected) {
    return (
      <div className="grid gap-3">
        <button
          type="button"
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-foreground"
          onClick={() => setSelectedId(null)}
        >
          <ChevronLeft className="h-4 w-4" />
          {t("artifacts.back")}
        </button>
        <ArtifactViewer artifact={selected} />
      </div>
    )
  }

  return (
    <div className="grid gap-4" data-testid="progress-tab">
      <section className="grid gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("progress.tasks")}
        </h3>
        <TodoChecklist todos={latestTodoArtifact ? todosFromArtifact(latestTodoArtifact) : []} />
      </section>

      {otherArtifacts.length ? (
        <section className="grid gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("artifacts.title")}
          </h3>
          <div className="grid gap-2">
            {otherArtifacts.map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                onClick={() => setSelectedId(artifact.id)}
                className="flex w-full items-start gap-3 rounded-2xl border border-border/70 bg-card px-3 py-2.5 text-left transition-colors hover:border-border hover:bg-muted/40"
              >
                <ArtifactIcon type={artifact.type} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-foreground">
                    {artifact.title}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {artifact.summary || artifactTypeLabel(t, artifact.type)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
