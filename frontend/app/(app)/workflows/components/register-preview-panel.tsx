import { useTranslations } from "next-intl"
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
} from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import {
  getContainerRegistryLabel,
  getContainerRegistrySelectValue,
} from "@/lib/registry-utils"
import type { ContainerRegistryConfig, ValidateWorkflowResponse } from "@/lib/types"
import { DagPanel } from "@/components/bioinfoflow/dag/dag-panel"
import { ValidationErrorList } from "./register-sub-components"
import type { EngineType, LocalImportMode, SourceType } from "./register-form-hook"

interface RegisterPreviewPanelProps {
  pipelineName: string
  localFileName: string
  localImportMode: LocalImportMode
  bundleLabel: string
  bundleFileCount: number
  entrypointRelpath: string
  engine: EngineType
  sourceType: SourceType
  version: string
  imageRegistries: ContainerRegistryConfig[]
  selectedRegistry: string
  hasEditor: boolean
  isValidating: boolean
  validationResult: ValidateWorkflowResponse | null
  onErrorClick: (line: number) => void
}

export function RegisterPreviewPanel({
  pipelineName,
  localFileName,
  localImportMode,
  bundleLabel,
  bundleFileCount,
  entrypointRelpath,
  engine,
  sourceType,
  version,
  imageRegistries,
  selectedRegistry,
  hasEditor,
  isValidating,
  validationResult,
  onErrorClick,
}: RegisterPreviewPanelProps) {
  const tWorkflows = useTranslations("workflows")

  const localEntrypointName = entrypointRelpath.split("/").pop() ?? entrypointRelpath
  const inferredLocalName =
    localImportMode === "bundle"
      ? localEntrypointName.replace(/\.(nf|wdl)$/i, "")
      : localFileName.replace(/\.(nf|wdl)$/i, "")
  const previewName = pipelineName.trim() || inferredLocalName || "\u2014"
  const previewEngine = engine === "wdl" ? "WDL" : "Nextflow"
  const selectedRegistryConfig = imageRegistries.find(
    (registry) => getContainerRegistrySelectValue(registry) === selectedRegistry,
  )
  const showImageRegistryPreview =
    imageRegistries.length > 0 || selectedRegistry.trim().length > 0
  const imageRegistryLabel = selectedRegistry
    ? getContainerRegistryLabel(
        selectedRegistryConfig ?? { name: selectedRegistry, registry: selectedRegistry },
      )
    : tWorkflows("registerDialog.registry.automatic")

  return (
    <aside className="relative rounded-2xl border border-border/60 bg-card/50 p-5 xl:sticky xl:top-0">
      <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-foreground/10 to-transparent" />
      <div className="rounded-xl border border-border/60 bg-background/80 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-border/40 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {tWorkflows("registerDialog.preview.title")}
        </div>
        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{tWorkflows("registerDialog.preview.nameLabel")}</span>
            <span className="font-medium text-foreground">{previewName}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{tWorkflows("engine")}</span>
            <Badge variant="outline" className={`text-xs-tight ${engine === "wdl" ? "bg-info/5 text-info border-info/20" : "bg-success/5 text-success border-success/20"}`}>
              {previewEngine}
            </Badge>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{tWorkflows("source")}</span>
            <span className="font-medium text-foreground">{sourceType}</span>
          </div>
          {showImageRegistryPreview ? (
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="text-muted-foreground">{tWorkflows("registerDialog.preview.imageRegistry")}</span>
              <span className="truncate text-right font-medium text-foreground">{imageRegistryLabel}</span>
            </div>
          ) : null}
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{tWorkflows("version")}</span>
            <span className="font-medium text-foreground/60">{version.trim() || tWorkflows("registerDialog.preview.latest")}</span>
          </div>
        </div>
      </div>

      {sourceType === "local" && localImportMode === "bundle" && bundleLabel ? (
        <div className="mt-4 rounded-xl border border-success/20 bg-success/5 p-3 text-sm text-foreground">
          <p className="font-medium">
            {tWorkflows("registerDialog.preview.bundleName", {
              name: bundleLabel,
              count: bundleFileCount,
            })}
          </p>
          {entrypointRelpath ? (
            <p className="mt-1 text-muted-foreground">
              {tWorkflows("registerDialog.preview.entrypointRelpath", {
                path: entrypointRelpath,
              })}
            </p>
          ) : null}
        </div>
      ) : localFileName ? (
        <div className="mt-4 rounded-xl border border-success/20 bg-success/5 p-3 text-sm text-foreground">
          <p className="font-medium">
            {tWorkflows("registerDialog.preview.fileName", {
              name: localFileName,
            })}
          </p>
          <p className="mt-1 text-muted-foreground">
            {tWorkflows("registerDialog.preview.detectedEngine", {
              engine,
            })}
          </p>
        </div>
      ) : null}
      {/* validation status section */}
      {hasEditor && isValidating && (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {tWorkflows("registerDialog.editor.autoValidating")}
        </div>
      )}

      {hasEditor &&
        validationResult &&
        !validationResult.valid &&
        validationResult.errors?.length > 0 && (
          <div className="mt-4">
            <ValidationErrorList
              errors={validationResult.errors}
              onErrorClick={onErrorClick}
            />
          </div>
        )}

      {hasEditor && validationResult?.valid && validationResult.dag && (
        <div className="mt-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {tWorkflows("registerDialog.preview.dagPreviewTitle")}
          </p>
          <div className="h-[250px] overflow-hidden rounded-2xl border border-border/60">
            <DagPanel dag={validationResult.dag} variant="embedded" showHeader={false} />
          </div>
        </div>
      )}

      {hasEditor && !isValidating && !validationResult && (
        <div className="mt-4 text-xs text-muted-foreground">
          {tWorkflows("registerDialog.preview.dagPreviewEmpty")}
        </div>
      )}
    </aside>
  )
}

export function ValidationBadge({
  isValidating,
  validationResult,
}: {
  isValidating: boolean
  validationResult: ValidateWorkflowResponse | null
}) {
  const tWorkflows = useTranslations("workflows")

  if (isValidating) {
    return (
      <Badge variant="outline" className="gap-1 border-info/20 bg-info/5 text-info">
        <Loader2 className="h-3 w-3 animate-spin" />
        {tWorkflows("registerDialog.editor.autoValidating")}
      </Badge>
    )
  }
  if (validationResult?.valid) {
    return (
      <Badge variant="outline" className="gap-1 border-success/20 bg-success/5 text-success">
        <CheckCircle2 className="h-3 w-3" />
        {tWorkflows("registerDialog.editor.syntaxOk")}
      </Badge>
    )
  }
  if (validationResult && !validationResult.valid) {
    return (
      <Badge variant="outline" className="gap-1 border-destructive/30 bg-destructive/5 text-destructive">
        <AlertCircle className="h-3 w-3" />
        {tWorkflows("registerDialog.editor.errorsFound", {
          count: validationResult.errors?.length ?? 0,
        })}
      </Badge>
    )
  }
  return null
}
