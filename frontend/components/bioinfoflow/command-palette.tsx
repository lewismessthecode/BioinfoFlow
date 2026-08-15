"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { AgentSessionSummary } from "@/lib/agent/client"
import type { Project, Run } from "@/lib/types"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { toast } from "sonner"

type CommandPaletteProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter()
  const tPalette = useTranslations("commandPalette")
  const {
    selectedProjectId,
    setSelectedProjectId,
    setConversationProjectId,
    setActiveConversationId,
  } = useProjectContext()
  const workspaceShell = useWorkspaceShell()
  const [runs, setRuns] = useState<Run[]>([])
  const projects = workspaceShell.projects
  const defaultProjectId = workspaceShell.defaultProject?.id ?? null
  const conversations = useMemo(() => {
    const seen = new Set<string>()
    const result: AgentSessionSummary[] = []
    for (const group of workspaceShell.projectConversations.values()) {
      for (const session of group) {
        if (seen.has(session.id)) continue
        seen.add(session.id)
        result.push(session)
      }
    }
    return result
  }, [workspaceShell.projectConversations])

  const fetchPaletteData = useCallback(async () => {
    try {
      const runsResponse = await apiRequest<Run[]>("/runs", {
        params: { limit: 20, project_id: selectedProjectId || undefined },
      })
      setRuns(runsResponse.data)
    } catch (error) {
      const message = getApiErrorMessage(error, tPalette("errors.loadFailed"))
      toast.error(message)
    }
  }, [selectedProjectId, tPalette])

  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchPaletteData()
    }
  }, [open, fetchPaletteData])

  const handleSelectProject = (project: Project) => {
    setSelectedProjectId(project.id)
    setConversationProjectId(project.id)
    setActiveConversationId("")
    onOpenChange(false)
    router.push("/agent")
  }

  const handleSelectConversation = (conversation: AgentSessionSummary) => {
    const projectId = conversation.project_id ?? defaultProjectId ?? ""
    if (projectId === defaultProjectId) {
      setSelectedProjectId("")
    } else {
      setSelectedProjectId(projectId)
    }
    setConversationProjectId(projectId)
    setActiveConversationId(conversation.id)
    onOpenChange(false)
    router.push(`/agent/${conversation.id}`)
  }

  const handleNewConversation = async () => {
    try {
      const targetProjectId = selectedProjectId || defaultProjectId
      if (!targetProjectId) {
        toast.error(tPalette("errors.createConversationFailed"))
        return
      }
      const resolvedProjectId = String(targetProjectId)
      if (resolvedProjectId === defaultProjectId) {
        setSelectedProjectId("")
      } else {
        setSelectedProjectId(resolvedProjectId)
      }
      setConversationProjectId(resolvedProjectId)
      setActiveConversationId("")
      onOpenChange(false)
      router.push("/agent")
    } catch (error) {
      const message = getApiErrorMessage(error, tPalette("errors.createConversationFailed"))
      toast.error(message)
    }
  }

  const projectMap = useMemo(
    () => new Map(projects.map((p) => [String(p.id), p.name])),
    [projects],
  )

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder={tPalette("searchPlaceholder")}
        aria-label={tPalette("searchAriaLabel")}
      />
      <CommandList>
        <CommandEmpty>{tPalette("empty")}</CommandEmpty>

        <CommandGroup heading={tPalette("groups.actions")}>
          <CommandItem onSelect={handleNewConversation}>{tPalette("actions.newConversation")}</CommandItem>
        </CommandGroup>

        <CommandSeparator />
        <CommandGroup heading={tPalette("groups.projects")}>
          {projects.map((project) => (
            <CommandItem key={project.id} onSelect={() => handleSelectProject(project)}>
              {project.name}
            </CommandItem>
          ))}
        </CommandGroup>

        {conversations.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading={tPalette("groups.conversations")}>
              {conversations.map((conversation, index) => (
                <CommandItem key={conversation.id} onSelect={() => handleSelectConversation(conversation)}>
                  <span className="truncate">
                    {conversation.title || tPalette("conversationFallback", { index: index + 1 })}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {projectMap.get(String(conversation.project_id)) || ""}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {runs.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading={tPalette("groups.runs")}>
              {runs.map((run) => (
                <CommandItem key={run.run_id} onSelect={() => router.push(`/runs?highlight=${run.run_id}`)}>
                  {run.run_id}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

      </CommandList>
    </CommandDialog>
  )
}
