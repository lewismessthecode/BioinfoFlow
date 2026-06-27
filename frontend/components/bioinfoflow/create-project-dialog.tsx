"use client"

import { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronDown, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { DirectoryBrowser } from "@/components/bioinfoflow/directory-browser"
import { fetchRemoteConnections, type RemoteConnection } from "@/lib/demo-connections"

type ProjectCreateMode = "local" | "remote"

interface CreateProjectDialogProps {
  collapsed: boolean
  onCreateProject: (data: {
    name: string
    description: string
    projectType?: ProjectCreateMode
    storageOverridePath?: string
    remoteConnectionId?: string
    remoteRootPath?: string
  }) => Promise<void>
  externalOpen?: boolean
  onExternalOpenChange?: (open: boolean) => void
  hideTrigger?: boolean
}

export function CreateProjectDialog({
  collapsed,
  onCreateProject,
  externalOpen,
  onExternalOpenChange,
  hideTrigger = false,
}: CreateProjectDialogProps) {
  const tSidebar = useTranslations("sidebar")
  const tCommon = useTranslations("common")
  const [internalOpen, setInternalOpen] = useState(false)

  const createOpen = externalOpen ?? internalOpen
  const setCreateOpen = (open: boolean) => {
    setInternalOpen(open)
    onExternalOpenChange?.(open)
  }
  const [isCreating, setIsCreating] = useState(false)
  const [newProjectName, setNewProjectName] = useState("")
  const [newProjectDescription, setNewProjectDescription] = useState("")
  const [newProjectWorkspace, setNewProjectWorkspace] = useState("")
  const [projectType, setProjectType] = useState<ProjectCreateMode>("local")
  const [remoteConnections, setRemoteConnections] = useState<RemoteConnection[]>([])
  const [remoteConnectionsLoading, setRemoteConnectionsLoading] = useState(false)
  const [remoteConnectionsLoadFailed, setRemoteConnectionsLoadFailed] = useState(false)
  const [remoteConnectionId, setRemoteConnectionId] = useState("")
  const [remoteRootPath, setRemoteRootPath] = useState("")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [browseOpen, setBrowseOpen] = useState(false)

  const resetCreateForm = () => {
    setNewProjectName("")
    setNewProjectDescription("")
    setNewProjectWorkspace("")
    setProjectType("local")
    setRemoteConnectionId("")
    setRemoteRootPath("")
    setShowAdvanced(false)
  }

  useEffect(() => {
    if (!createOpen || projectType !== "remote") return
    if (remoteConnections.length > 0) return
    let cancelled = false
    setRemoteConnectionsLoading(true)
    setRemoteConnectionsLoadFailed(false)
    void fetchRemoteConnections()
      .then((connections) => {
        if (cancelled) return
        setRemoteConnections(connections)
      })
      .catch(() => {
        if (cancelled) return
        setRemoteConnections([])
        setRemoteConnectionsLoadFailed(true)
      })
      .finally(() => {
        if (!cancelled) setRemoteConnectionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [createOpen, projectType, remoteConnections.length])

  useEffect(() => {
    if (!createOpen || projectType !== "remote" || remoteConnections.length === 0) return
    setRemoteConnectionId((current) => (
      remoteConnections.some((connection) => connection.id === current)
        ? current
        : remoteConnections[0]?.id || ""
    ))
  }, [createOpen, projectType, remoteConnections])

  const selectedRemoteConnection = remoteConnections.find(
    (connection) => connection.id === remoteConnectionId,
  )
  const canCreate = Boolean(
    newProjectName.trim()
      && (projectType === "local" || (remoteConnectionId && remoteRootPath.trim())),
  )

  const handleCreate = async () => {
    if (!newProjectName.trim()) return
    if (projectType === "remote" && (!remoteConnectionId || !remoteRootPath.trim())) return

    setIsCreating(true)
    try {
      await onCreateProject({
        name: newProjectName,
        description: newProjectDescription,
        ...(projectType === "remote"
          ? {
              projectType,
              remoteConnectionId,
              remoteRootPath: remoteRootPath.trim(),
            }
          : newProjectWorkspace.trim()
            ? {
                storageOverridePath: newProjectWorkspace.trim(),
              }
            : {}),
      })
      setCreateOpen(false)
      resetCreateForm()
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <Dialog
      open={createOpen}
      onOpenChange={(open) => {
        setCreateOpen(open)
        if (!open) {
          resetCreateForm()
        }
      }}
    >
      {!hideTrigger && (
        collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <DialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="mt-2 w-full h-9 text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                  aria-label={tSidebar("newProject")}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </DialogTrigger>
            </TooltipTrigger>
            <TooltipContent side="right">{tSidebar("newProject")}</TooltipContent>
          </Tooltip>
        ) : (
          <DialogTrigger asChild>
            <Button
              variant="ghost"
              className="mt-3 w-full justify-start gap-3 font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/50"
              aria-label={tSidebar("newProject")}
            >
              <Plus className="h-4 w-4" />
              <span>{tSidebar("newProject")}</span>
            </Button>
          </DialogTrigger>
        )
      )}
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{tSidebar("createProject")}</DialogTitle>
          <DialogDescription>{tSidebar("projectDescription")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Project Name */}
          <div className="space-y-2">
            <Label htmlFor="project-name">{tSidebar("projectName")}</Label>
            <Input
              id="project-name"
              placeholder={tSidebar("placeholders.projectName")}
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
              autoFocus
            />
            {newProjectName.trim() && (
              <p className="text-xs text-muted-foreground" aria-label={tSidebar("workspacePreviewLabel")}>
                {projectType === "remote"
                  ? tSidebar("remoteStoragePreview", {
                      host: selectedRemoteConnection?.name || tSidebar("remoteHostFallback"),
                      path: remoteRootPath.trim() || "-",
                    })
                  : tSidebar("storageManagedPreview")}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="project-description">{tSidebar("projectDescription")}</Label>
            <Input
              id="project-description"
              placeholder={tSidebar("placeholders.projectDescription")}
              value={newProjectDescription}
              onChange={(event) => setNewProjectDescription(event.target.value)}
            />
          </div>

          {/* Project Type */}
          <div className="grid gap-2">
            <Label>{tSidebar("projectType")}</Label>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={tSidebar("projectType")}>
              {(["local", "remote"] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={projectType === type}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-left transition-colors",
                    projectType === type
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border/70 text-muted-foreground hover:bg-secondary/40",
                  )}
                  onClick={() => setProjectType(type)}
                >
                  <span className="block text-sm font-medium">
                    {tSidebar(`projectTypes.${type}.title`)}
                  </span>
                  <span className="mt-1 block text-xs leading-4">
                    {tSidebar(`projectTypes.${type}.description`)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {projectType === "local" ? (
            <div className="rounded-lg border border-border/60">
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium text-foreground hover:bg-secondary/30 transition-colors rounded-lg"
                onClick={() => setShowAdvanced((prev) => !prev)}
              >
                {tSidebar("advancedSettings")}
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-muted-foreground transition-transform duration-200",
                    showAdvanced && "rotate-180",
                  )}
                />
              </button>

              <div
                className={cn(
                  "grid transition-[grid-template-rows] duration-200",
                  showAdvanced ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                )}
              >
                <div className="overflow-hidden">
                  <div className="px-4 pb-4 pt-1 space-y-2">
                    <Label htmlFor="workspace-path">{tSidebar("workspacePath")}</Label>
                    <div className="flex gap-2">
                      <Input
                        id="workspace-path"
                        placeholder={tSidebar("placeholders.workspacePath")}
                        value={newProjectWorkspace}
                        onChange={(event) => setNewProjectWorkspace(event.target.value)}
                        className="flex-1"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0"
                        onClick={() => setBrowseOpen(true)}
                      >
                        {tSidebar("browseDirectories")}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {tSidebar("hints.storageOverridePath")}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4 rounded-lg border border-border/60 p-4">
              <div className="space-y-2">
                <Label htmlFor="remote-host">{tSidebar("remoteHost")}</Label>
                <select
                  id="remote-host"
                  value={remoteConnectionId}
                  onChange={(event) => setRemoteConnectionId(event.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={remoteConnectionsLoading || remoteConnections.length === 0}
                >
                  {remoteConnectionsLoading ? (
                    <option value="">{tSidebar("loadingRemoteHosts")}</option>
                  ) : remoteConnectionsLoadFailed ? (
                    <option value="">{tSidebar("errors.remoteHostsLoadFailed")}</option>
                  ) : remoteConnections.length ? (
                    remoteConnections.map((connection) => (
                      <option key={connection.id} value={connection.id}>
                        {connection.name} ({connection.username}@{connection.host})
                      </option>
                    ))
                  ) : (
                    <option value="">{tSidebar("noRemoteHosts")}</option>
                  )}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="remote-root-path">{tSidebar("remotePath")}</Label>
                <div className="flex gap-2">
                  <Input
                    id="remote-root-path"
                    placeholder={tSidebar("placeholders.remotePath")}
                    value={remoteRootPath}
                    onChange={(event) => setRemoteRootPath(event.target.value)}
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setBrowseOpen(true)}
                    disabled={!remoteConnectionId}
                  >
                    {tSidebar("browseDirectories")}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {tSidebar("hints.remotePath")}
                </p>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCreateOpen(false)}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={handleCreate} disabled={isCreating || !canCreate}>
            {isCreating ? tCommon("loading") : tSidebar("createProject")}
          </Button>
        </DialogFooter>
      </DialogContent>

      <DirectoryBrowser
        open={browseOpen}
        onOpenChange={setBrowseOpen}
        initialPath={projectType === "remote" ? remoteRootPath || "/" : newProjectWorkspace || undefined}
        onSelect={(path) => {
          if (projectType === "remote") {
            setRemoteRootPath(path)
          } else {
            setNewProjectWorkspace(path)
          }
        }}
        source={projectType === "remote" ? "remote" : "local"}
        remoteConnectionId={remoteConnectionId || undefined}
      />
    </Dialog>
  )
}
