"use client"

import { useState } from "react"
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

interface CreateProjectDialogProps {
  collapsed: boolean
  onCreateProject: (data: {
    name: string
    description: string
    storageOverridePath?: string
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
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [browseOpen, setBrowseOpen] = useState(false)

  const resetCreateForm = () => {
    setNewProjectName("")
    setNewProjectDescription("")
    setNewProjectWorkspace("")
    setShowAdvanced(false)
  }

  const handleCreate = async () => {
    if (!newProjectName.trim()) return

    setIsCreating(true)
    try {
      await onCreateProject({
        name: newProjectName,
        description: newProjectDescription,
        storageOverridePath: newProjectWorkspace.trim() || undefined,
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
      <DialogContent className="sm:max-w-md">
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
                {tSidebar("storageManagedPreview")}
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

          {/* Advanced Settings (collapsible) */}
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
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCreateOpen(false)}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={handleCreate} disabled={isCreating}>
            {isCreating ? tCommon("loading") : tSidebar("createProject")}
          </Button>
        </DialogFooter>
      </DialogContent>

      <DirectoryBrowser
        open={browseOpen}
        onOpenChange={setBrowseOpen}
        initialPath={newProjectWorkspace || undefined}
        onSelect={(path) => setNewProjectWorkspace(path)}
      />
    </Dialog>
  )
}
