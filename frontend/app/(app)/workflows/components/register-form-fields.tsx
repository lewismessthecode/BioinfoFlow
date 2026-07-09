import { type ChangeEvent, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import {
  Boxes,
  Check,
  FileCode2,
  FolderInput,
  ListTree,
  Package,
  Sparkles,
} from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  AUTOMATIC_REGISTRY_VALUE,
  getContainerRegistryLabel,
  getContainerRegistrySelectValue,
} from "@/lib/registry-utils"
import { cn } from "@/lib/utils"
import type { ContainerRegistryConfig, ValidateWorkflowResponse } from "@/lib/types"
import { WorkflowCodeEditor } from "./workflow-code-editor"
import type { ReactCodeMirrorRef } from "@uiw/react-codemirror"
import { ValidationBadge } from "./register-preview-panel"
import type { LocalImportMode, SourceType } from "./register-form-hook"

const SOURCE_ACCENTS: Record<
  SourceType,
  { gradient: string; iconBackground: string; iconColor: string }
> = {
  "nf-core": {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--primary) 10%, transparent), transparent 70%)",
    iconBackground:
      "color-mix(in srgb, var(--primary) 12%, transparent)",
    iconColor: "var(--primary)",
  },
  github: {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--ring) 12%, transparent), transparent 70%)",
    iconBackground:
      "color-mix(in srgb, var(--ring) 12%, transparent)",
    iconColor: "var(--ring)",
  },
  local: {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--accent) 92%, transparent), transparent 70%)",
    iconBackground:
      "color-mix(in srgb, var(--foreground) 8%, transparent)",
    iconColor: "var(--foreground)",
  },
}

interface SourceCard {
  type: SourceType
  icon: typeof Sparkles
  label: string
  description: string
}

interface RegisterFormFieldsProps {
  sourceType: SourceType
  engine: string
  pipelineName: string
  version: string
  description: string
  imageRegistries: ContainerRegistryConfig[]
  selectedRegistry: string
  localImportMode: LocalImportMode
  localFileName: string
  bundleLabel: string
  bundleFileCount: number
  entrypointCandidates: string[]
  entrypointRelpath: string
  sourceLabel: string
  sourcePlaceholder: string
  hasEditor: boolean
  editorContent: string | null
  editorRef: React.RefObject<ReactCodeMirrorRef | null>
  isValidating: boolean
  validationResult: ValidateWorkflowResponse | null
  onSourceChange: (type: SourceType) => void
  onEngineChange: (engine: "nextflow" | "wdl") => void
  onPipelineNameChange: (value: string) => void
  onVersionChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  onSelectedRegistryChange: (value: string) => void
  onLocalImportModeChange: (mode: LocalImportMode) => void
  onLocalFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  onBundleDirectoryChange: (event: ChangeEvent<HTMLInputElement>) => void
  onEntrypointRelpathChange: (value: string) => void
  onEditorChange: (content: string) => void
  onChangeFile: () => void
}

export function RegisterFormFields({
  sourceType,
  engine,
  pipelineName,
  version,
  description,
  imageRegistries,
  selectedRegistry,
  localImportMode,
  localFileName,
  bundleLabel,
  bundleFileCount,
  entrypointCandidates,
  entrypointRelpath,
  sourceLabel,
  sourcePlaceholder,
  hasEditor,
  editorContent,
  editorRef,
  isValidating,
  validationResult,
  onSourceChange,
  onEngineChange,
  onPipelineNameChange,
  onVersionChange,
  onDescriptionChange,
  onSelectedRegistryChange,
  onLocalImportModeChange,
  onLocalFileChange,
  onBundleDirectoryChange,
  onEntrypointRelpathChange,
  onEditorChange,
  onChangeFile,
}: RegisterFormFieldsProps) {
  const tWorkflows = useTranslations("workflows")
  const bundleInputRef = useRef<HTMLInputElement>(null)
  const [entrypointDialogOpen, setEntrypointDialogOpen] = useState(false)
  const selectedEntrypointLabel = entrypointRelpath || tWorkflows("registerDialog.placeholders.entrypointSelect")
  const entrypointItems = useMemo(
    () =>
      entrypointCandidates.map((candidate) => ({
        path: candidate,
        display: candidate.split("/").pop() || candidate,
      })),
    [entrypointCandidates],
  )

  const sourceCards: SourceCard[] = [
    {
      type: "nf-core",
      icon: Sparkles,
      label: "nf-core",
      description: tWorkflows("registerDialog.sourceDescriptions.nfCore"),
    },
    {
      type: "github",
      icon: Boxes,
      label: "GitHub",
      description: tWorkflows("registerDialog.sourceDescriptions.github"),
    },
    {
      type: "local",
      icon: FolderInput,
      label: tWorkflows("registerDialog.sourceTypes.local"),
      description: tWorkflows("registerDialog.sourceDescriptions.local"),
    },
  ]

  return (
    <>
      <div className="space-y-1.5">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-muted/60 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          <Sparkles className="h-3 w-3 text-primary" />
          {tWorkflows("registerDialog.importSource")}
        </div>
      </div>

      {/* source cards */}
      <div className="space-y-2">
        <Label>{tWorkflows("registerDialog.fields.sourceType")}</Label>
        <div className="grid gap-2.5 md:grid-cols-3">
          {sourceCards.map(({ type, icon: Icon, label, description }) => {
            const accent = SOURCE_ACCENTS[type]
            return (
              <button
                key={type}
                type="button"
                aria-label={label}
                onClick={() => onSourceChange(type)}
                className={cn(
                  "group relative min-h-[136px] rounded-2xl border p-3.5 text-left transition-all duration-150",
                  sourceType === type
                    ? "border-foreground/20 shadow-sm"
                    : "border-border/60 bg-background hover:border-foreground/15 hover:shadow-sm",
                )}
                style={
                  sourceType === type
                    ? { backgroundImage: accent.gradient }
                    : undefined
                }
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                    style={{
                      backgroundColor: accent.iconBackground,
                      color: accent.iconColor,
                    }}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  {sourceType === type && (
                    <div className="flex h-5 w-5 items-center justify-center rounded-full bg-foreground">
                      <Check className="h-3 w-3 text-background" />
                    </div>
                  )}
                </div>
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">{label}</p>
                  <p className="line-clamp-3 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {imageRegistries.length > 0 ? (
        <div className="space-y-2">
          <Label htmlFor="workflow-image-registry">
            {tWorkflows("registerDialog.fields.imageRegistry")}
          </Label>
          <select
            id="workflow-image-registry"
            value={selectedRegistry}
            onChange={(event) => onSelectedRegistryChange(event.target.value)}
            className={cn(
              "border-input h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow]",
              "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
            )}
          >
            <option value={AUTOMATIC_REGISTRY_VALUE}>
              {tWorkflows("registerDialog.registry.automatic")}
            </option>
            {imageRegistries.map((registry) => {
              const value = getContainerRegistrySelectValue(registry)
              return (
                <option key={registry.id ?? value} value={value}>
                  {getContainerRegistryLabel(registry)}
                </option>
              )
            })}
          </select>
          <p className="text-xs text-muted-foreground">
            {tWorkflows("registerDialog.registry.hint")}
          </p>
        </div>
      ) : null}

      {/* pipeline name + version */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="pipeline-name">{sourceLabel}</Label>
          <Input
            id="pipeline-name"
            placeholder={sourcePlaceholder}
            value={pipelineName}
            onChange={(e) => onPipelineNameChange(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="version">{tWorkflows("version")}</Label>
          <Input
            id="version"
            placeholder={tWorkflows("registerDialog.placeholders.version")}
            value={version}
            onChange={(e) => onVersionChange(e.target.value)}
          />
        </div>
      </div>

      {/* description */}
      <div className="space-y-2">
        <Label htmlFor="workflow-description">{tWorkflows("registerDialog.fields.description")}</Label>
        <Textarea
          id="workflow-description"
          placeholder={tWorkflows("registerDialog.placeholders.description")}
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={1}
          className="resize-none"
        />
      </div>

      {/* file upload OR editor */}
      {sourceType === "local" && (
        <div className="space-y-4 rounded-2xl border border-border/60 bg-muted/20 p-4">
          <div className="space-y-2">
            <Label>{tWorkflows("registerDialog.fields.localImportMode")}</Label>
            <div className="inline-flex w-full rounded-lg border border-border/60 bg-background/80 p-0.5">
              {([
                {
                  value: "bundle",
                  label: tWorkflows("registerDialog.localModes.bundle"),
                  icon: Package,
                },
                {
                  value: "single-file",
                  label: tWorkflows("registerDialog.localModes.singleFile"),
                  icon: FileCode2,
                },
              ] as const).map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onLocalImportModeChange(value)}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150",
                    localImportMode === value
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {localImportMode === "bundle" ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="workflow-bundle-upload">
                  {tWorkflows("registerDialog.fields.bundleUpload")}
                </Label>
                <input
                  ref={bundleInputRef}
                  id="workflow-bundle-upload"
                  type="file"
                  multiple
                  className="sr-only"
                  onChange={onBundleDirectoryChange}
                  {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                />
                <div className="flex gap-2">
                  <Input
                    value={bundleLabel ? `${bundleLabel} (${bundleFileCount})` : ""}
                    placeholder={tWorkflows("registerDialog.placeholders.bundleUpload")}
                    readOnly
                    className="flex-1"
                  />
                  <Button type="button" variant="outline" onClick={() => bundleInputRef.current?.click()}>
                    {tWorkflows("registerDialog.actions.chooseBundle")}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {tWorkflows("registerDialog.hints.bundlePath")}
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="workflow-entrypoint-display">
                  {tWorkflows("registerDialog.fields.entrypointSelect")}
                </Label>
                <div className="flex gap-2">
                  <Input
                    id="workflow-entrypoint-display"
                    value={selectedEntrypointLabel}
                    placeholder={tWorkflows("registerDialog.placeholders.entrypointSelect")}
                    readOnly
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setEntrypointDialogOpen(true)}
                    disabled={entrypointItems.length === 0}
                  >
                    {tWorkflows("registerDialog.actions.chooseEntrypoint")}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {tWorkflows("registerDialog.hints.entrypointRelpath")}
                </p>
              </div>
            </div>
          ) : !hasEditor ? (
            <div className="space-y-2">
              <Label htmlFor="workflow-file">
                {tWorkflows("registerDialog.fields.workflowFile")}
              </Label>
              <Input
                id="workflow-file"
                type="file"
                accept=".nf,.wdl"
                onChange={onLocalFileChange}
              />
              {localFileName && (
                <p className="text-xs text-muted-foreground">
                  {tWorkflows("registerDialog.selectedFile", { name: localFileName })}
                </p>
              )}
            </div>
          ) : null}
        </div>
      )}

      <Dialog open={entrypointDialogOpen} onOpenChange={setEntrypointDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{tWorkflows("registerDialog.entrypointBrowser.title")}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[360px] overflow-y-auto rounded-xl border border-border/60">
            {entrypointItems.length === 0 ? (
              <div className="px-4 py-6 text-sm text-muted-foreground">
                {tWorkflows("registerDialog.entrypointBrowser.empty")}
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {entrypointItems.map(({ path, display }) => (
                  <button
                    key={path}
                    type="button"
                    className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/30"
                    onClick={() => {
                      onEntrypointRelpathChange(path)
                      setEntrypointDialogOpen(false)
                    }}
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      {path.toLowerCase().endsWith(".wdl") ? (
                        <FileCode2 className="h-4 w-4" />
                      ) : (
                        <ListTree className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{display}</p>
                      <p className="truncate text-xs text-muted-foreground">{path}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {hasEditor && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label>{tWorkflows("registerDialog.editor.title")}</Label>
              <ValidationBadge
                isValidating={isValidating}
                validationResult={validationResult}
              />
            </div>
            <Button variant="ghost" size="sm" onClick={onChangeFile}>
              {tWorkflows("registerDialog.editor.changeFile")}
            </Button>
          </div>
          <WorkflowCodeEditor
            ref={editorRef}
            content={editorContent}
            onChange={onEditorChange}
            errors={validationResult?.errors ?? []}
            height="280px"
          />
        </div>
      )}

      {/* engine toggle */}
      <div className="space-y-2">
        <Label>{tWorkflows("engine")}</Label>
        <div className={cn(
          "inline-flex w-full rounded-lg border border-border/60 bg-muted/40 p-0.5",
          sourceType === "nf-core" && "opacity-60",
        )}>
          {(["nextflow", "wdl"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onEngineChange(value)}
              disabled={sourceType === "nf-core"}
              className={cn(
                "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-all duration-150",
                engine === value
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
                sourceType === "nf-core" && "cursor-not-allowed",
              )}
            >
              {value === "nextflow" ? "Nextflow" : "WDL"}
            </button>
          ))}
        </div>
        <div className="min-h-5 text-xs text-muted-foreground">
          {sourceType === "nf-core" ? tWorkflows("registerDialog.nfCoreHint") : null}
        </div>
      </div>
    </>
  )
}
