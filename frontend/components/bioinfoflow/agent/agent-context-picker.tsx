"use client"

import { ChangeEvent, useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Activity,
  File,
  Folder,
  Loader2,
  Paperclip,
  Plus,
  Workflow,
} from "@/lib/icons"
import {
  searchAgentContext,
  uploadAgentAttachments,
  type AgentContextInput,
  type AgentContextKind,
  type AgentContextSearchItem,
} from "@/lib/agent/context"
import type { AppIcon } from "@/lib/icons"

const iconByKind: Record<Exclude<AgentContextKind, "attachment">, AppIcon> = {
  file: File,
  directory: Folder,
  workflow: Workflow,
  run: Activity,
}

export function AgentContextPicker({
  projectId,
  sessionId,
  ensureSession,
  onAdd,
  disabled = false,
}: {
  projectId: string | null
  sessionId: string | null
  ensureSession: () => Promise<string>
  onAdd: (input: AgentContextInput) => void
  disabled?: boolean
}) {
  const t = useTranslations("agentContextPicker")
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<AgentContextSearchItem[]>([])
  const [searching, setSearching] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<"searchError" | "uploadError" | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open || !query.trim()) {
      setResults([])
      setSearching(false)
      setError((current) => (current === "searchError" ? null : current))
      return
    }

    const controller = new AbortController()
    const timeout = window.setTimeout(() => {
      setSearching(true)
      setError(null)
      void searchAgentContext({
        query: query.trim(),
        projectId,
        sessionId,
        signal: controller.signal,
      })
        .then((result) => setResults(result.results))
        .catch(() => {
          if (!controller.signal.aborted) {
            setResults([])
            setError("searchError")
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, 150)

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [open, projectId, query, sessionId])

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen) {
      setQuery("")
      setResults([])
      setSearching(false)
      setError(null)
    }
  }

  const selectResult = (item: AgentContextSearchItem) => {
    onAdd({ ...item })
    setOpen(false)
    setQuery("")
  }

  const upload = async (
    event: ChangeEvent<HTMLInputElement>,
    kind: "file" | "folder",
  ) => {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ""
    if (files.length === 0) return

    setUploading(true)
    setError(null)
    try {
      const resolvedSessionId = sessionId ?? (await ensureSession())
      const relativePaths =
        kind === "folder"
          ? files.map((file) => file.webkitRelativePath || file.name)
          : undefined
      const uploadKind =
        kind === "file" && files.length === 1 && files[0].type.startsWith("image/")
          ? "image"
          : kind
      const parts = await uploadAgentAttachments({
        sessionId: resolvedSessionId,
        kind: uploadKind,
        files,
        ...(relativePaths ? { relativePaths } : {}),
        source: "upload",
      })
      const folderLabel = relativePaths?.[0]?.split("/")[0] || files[0].name
      for (const [index, part] of parts.entries()) {
        onAdd({
          id: `attachment:${part.attachment_id}`,
          kind: "attachment",
          label: kind === "folder" ? folderLabel : files[index]?.name ?? files[0].name,
          detail: kind === "folder" && files.length > 1 ? `${files.length} files` : null,
          input_part: part,
        })
      }
      setOpen(false)
    } catch {
      setError("uploadError")
    } finally {
      setUploading(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={disabled || uploading}
          aria-label={t("add")}
        >
          {uploading ? (
            <Loader2
              data-icon="inline-start"
              aria-hidden="true"
              className="animate-spin motion-reduce:animate-none"
            />
          ) : (
            <Plus data-icon="inline-start" aria-hidden="true" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        className="w-[min(24rem,calc(100vw-1.5rem))] p-0 shadow-xs motion-reduce:animate-none"
      >
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder={t("searchPlaceholder")}
          />
          <CommandList>
            {query.trim() ? (
              <>
                {searching ? (
                  <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
                    <Loader2
                      aria-hidden="true"
                      className="animate-spin motion-reduce:animate-none"
                    />
                    {t("searching")}
                  </div>
                ) : null}
                {!searching && results.length === 0 && !error ? (
                  <CommandEmpty>{t("empty")}</CommandEmpty>
                ) : null}
                {results.length > 0 ? (
                  <CommandGroup>
                    {results.map((item) => {
                      const Icon = iconByKind[item.kind]
                      return (
                        <CommandItem
                          key={item.id}
                          value={item.id}
                          onSelect={() => selectResult(item)}
                          className="items-start py-2"
                        >
                          <Icon aria-hidden="true" className="mt-0.5" />
                          <span className="min-w-0">
                            <span className="block truncate">{item.label}</span>
                            {item.detail ? (
                              <span className="block truncate text-xs text-muted-foreground">
                                {item.detail}
                              </span>
                            ) : null}
                          </span>
                        </CommandItem>
                      )
                    })}
                  </CommandGroup>
                ) : null}
              </>
            ) : null}
            <CommandSeparator />
            <CommandGroup>
              <CommandItem onSelect={() => fileInputRef.current?.click()}>
                <Paperclip aria-hidden="true" />
                {t("uploadFiles")}
              </CommandItem>
              <CommandItem onSelect={() => folderInputRef.current?.click()}>
                <Folder aria-hidden="true" />
                {t("uploadFolder")}
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
        {error ? (
          <p role="alert" className="border-t px-3 py-2 text-xs text-destructive">
            {t(error)}
          </p>
        ) : null}
        <input
          ref={fileInputRef}
          type="file"
          aria-label={t("uploadFiles")}
          multiple
          className="sr-only"
          tabIndex={-1}
          onChange={(event) => void upload(event, "file")}
        />
        <input
          type="file"
          aria-label={t("uploadFolder")}
          multiple
          data-folder
          className="sr-only"
          tabIndex={-1}
          ref={(element) => {
            folderInputRef.current = element
            element?.setAttribute("webkitdirectory", "")
          }}
          onChange={(event) => void upload(event, "folder")}
        />
      </PopoverContent>
    </Popover>
  )
}
