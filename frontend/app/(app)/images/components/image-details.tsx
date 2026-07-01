import {
  Copy,
  Download,
  RefreshCcw,
  Sparkles,
  FileArchive,
  Package2,
  Trash2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import { formatSize } from "@/lib/format-utils"
import { getDockerImageReference, getDockerPullCommand } from "@/lib/docker-image-utils"
import type { DockerImage } from "@/lib/types"
import { statusLabelKeys } from "./image-views"

/* ── empty states ───────────────────────────────────────── */

export function OnboardingImagesEmptyState({
  tImages,
  recommendedOpen,
  recommendedImages,
  onOpenRecommendations,
  onPull,
  onTarball,
  onChooseRecommended,
}: {
  tImages: (key: string) => string
  recommendedOpen: boolean
  recommendedImages: readonly string[]
  onOpenRecommendations: () => void
  onPull: () => void
  onTarball: () => void
  onChooseRecommended: (value: string) => void
}) {
  return (
    <section className="rounded-3xl border border-border/70 bg-[radial-gradient(circle_at_top_left,rgba(148,163,184,0.14),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.95),rgba(248,250,252,0.88))] p-7 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:bg-[radial-gradient(circle_at_top_left,rgba(148,163,184,0.08),transparent_42%),linear-gradient(180deg,rgba(30,30,32,0.95),rgba(24,24,27,0.88))] dark:shadow-[0_1px_2px_rgba(0,0,0,0.2)]">
      <div className="max-w-2xl">
        <Badge variant="secondary" className="mb-3 gap-1 text-xs-tight uppercase tracking-[0.18em]">
          <Sparkles className="h-3 w-3" />
          {tImages("shared")}
        </Badge>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">{tImages("empty.availableTitle")}</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{tImages("empty.availableDescription")}</p>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <Button className="justify-start" onClick={onPull}>
          <Download className="mr-2 h-4 w-4" />
          {tImages("empty.actions.pull")}
        </Button>
        <Button variant="outline" className="justify-start" onClick={onTarball}>
          <FileArchive className="mr-2 h-4 w-4" />
          {tImages("empty.actions.tarball")}
        </Button>
        <Button variant="outline" className="justify-start" onClick={onOpenRecommendations}>
          <Sparkles className="mr-2 h-4 w-4" />
          {tImages("empty.actions.recommended")}
        </Button>
      </div>

      {recommendedOpen && (
        <div className="mt-5 rounded-2xl border border-border/70 bg-background/70 p-4">
          <h3 className="text-sm font-semibold text-foreground">{tImages("empty.recommendedTitle")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{tImages("empty.recommendedDescription")}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {recommendedImages.map((image) => (
              <Button key={image} variant="outline" size="sm" onClick={() => onChooseRecommended(image)}>
                {image}
              </Button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export function UnavailableImagesEmptyState({
  tImages,
  onRefresh,
}: {
  tImages: (key: string) => string
  onRefresh: () => void
}) {
  return (
    <section className="rounded-3xl border border-warning/24 bg-warning/7 p-7 text-left">
      <h2 className="text-2xl font-semibold tracking-tight text-foreground">{tImages("empty.unavailableTitle")}</h2>
      <p className="mt-2 max-w-xl text-sm leading-6 text-warning-foreground/80">{tImages("empty.unavailableDescription")}</p>
      <Button variant="outline" className="mt-5" onClick={onRefresh}>
        <RefreshCcw className="mr-2 h-4 w-4" />
        {tImages("actions.refresh")}
      </Button>
    </section>
  )
}

/* ── details sheet ──────────────────────────────────────── */

export function ImageDetailsSheet({
  image,
  tImages,
  onPull,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
  onOpenChange,
}: {
  image: DockerImage | null
  tImages: (key: string, values?: Record<string, unknown>) => string
  onPull: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
  onOpenChange: (open: boolean) => void
}) {
  const imageReference = image ? getDockerImageReference(image) : ""
  const pullCommand = image ? getDockerPullCommand(image) : ""

  return (
    <Sheet open={Boolean(image)} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto overscroll-contain sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{tImages("details.title")}</SheetTitle>
          <SheetDescription>{tImages("details.description")}</SheetDescription>
        </SheetHeader>

        {image && (
          <div className="mt-6 space-y-5">
            <section className="rounded-xl border border-border/70 bg-background p-4">
              <div className="flex items-start gap-3">
                <div className="quiet-card-icon-shell quiet-card-icon-shell--artifact shrink-0">
                  <Package2 className="quiet-card-icon-glyph h-4 w-4" strokeWidth={1.8} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-all font-mono text-sm font-semibold text-foreground">{imageReference}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{tImages(statusLabelKeys[image.status])}</span>
                    <span aria-hidden="true">/</span>
                    <span>{formatSize(image.size_bytes)}</span>
                    <span aria-hidden="true">/</span>
                    <span className="font-mono">{image.tag}</span>
                  </div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  data-testid="image-details-copy-name"
                  onClick={() => onCopyName(image)}
                >
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  {tImages("actions.copyName")}
                </Button>
                <Button
                  type="button"
                  variant={image.status === "local" ? "outline" : "default"}
                  size="sm"
                  data-testid="image-details-pull"
                  disabled={image.status === "pulling"}
                  onClick={() => onPull(image)}
                >
                  <Download className="mr-1.5 h-3.5 w-3.5" />
                  {image.status === "pulling"
                    ? tImages("actions.pulling")
                    : image.status === "local"
                      ? tImages("actions.repull")
                      : tImages("actions.pull")}
                </Button>
              </div>
              {onDeleteLocal && image.status === "local" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-2 w-full justify-start text-destructive hover:text-destructive"
                  onClick={() => onDeleteLocal(image)}
                >
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                  {tImages("actions.deleteLocal")}
                </Button>
              ) : null}
            </section>

            <section className="rounded-xl border border-border/70 bg-muted/20 p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-foreground">{tImages("details.pullCommand")}</h3>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  data-testid="image-details-copy-pull-command"
                  onClick={() => onCopyPullCommand(image)}
                >
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  {tImages("details.copyCommand")}
                </Button>
              </div>
              <p className="mt-3 break-all rounded-lg border border-border/70 bg-background px-3 py-2 font-mono text-xs text-foreground">
                {pullCommand}
              </p>
            </section>

            <dl className="grid gap-4 rounded-xl border border-border/70 bg-muted/20 p-4 sm:grid-cols-2">
              <DetailField label={tImages("details.fields.name")} value={imageReference} fullWidth />
              <DetailField label={tImages("details.fields.registry")} value={image.registry} />
              <DetailField label={tImages("details.fields.tag")} value={image.tag} />
              <DetailField label={tImages("details.fields.size")} value={formatSize(image.size_bytes)} />
              <DetailField label={tImages("details.fields.status")} value={tImages(statusLabelKeys[image.status])} />
              <DetailField label={tImages("details.fields.updated")} value={formatSyncLabel(image.updated_at)} />
              {image.error_message && (
                <DetailField label={tImages("details.fields.error")} value={image.error_message} fullWidth />
              )}
            </dl>

            <DetailSection
              title={tImages("details.sections.labels")}
              items={image.labels ? Object.entries(image.labels).map(([key, value]) => `${key}: ${value}`) : []}
            />
            <DetailSection title={tImages("details.sections.environment")} items={image.env ?? []} />
            <DetailSection title={tImages("details.sections.entrypoint")} items={image.entrypoint ?? []} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

/* ── helper components ──────────────────────────────────── */

function DetailField({
  label,
  value,
  fullWidth = false,
}: {
  label: string
  value: string
  fullWidth?: boolean
}) {
  return (
    <div className={cn("space-y-1", fullWidth && "sm:col-span-2")}>
      <dt className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium text-foreground break-all">{value}</dd>
    </div>
  )
}

function DetailSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null
  }

  return (
    <section className="rounded-2xl border border-border/70 bg-background p-4">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        {items.map((item) => (
          <p key={item} className="break-all rounded-lg bg-muted/30 px-3 py-2">
            {item}
          </p>
        ))}
      </div>
    </section>
  )
}

export function formatSyncLabel(value?: string | null) {
  if (!value) {
    return "-"
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}
