import {
  Check,
  Cloud,
  Loader2,
  AlertCircle,
  HardDrive,
  Download,
  Package2,
  MoreHorizontal,
  Copy,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { cn } from "@/lib/utils"
import { formatSize } from "@/lib/format-utils"
import type { DockerImage, ImageStatus } from "@/lib/types"

export type ImageRepositoryGroup = {
  key: string
  label: string
  registry: string
  images: DockerImage[]
  primaryImage: DockerImage
  status: ImageStatus
}

type ImageTranslator = (key: string, values?: Record<string, unknown>) => string

const statusIcons: Record<ImageStatus, typeof Check> = {
  local: Check,
  remote: Cloud,
  pulling: Loader2,
  failed: AlertCircle,
}

const statusLabelKeys: Record<ImageStatus, string> = {
  local: "statuses.local",
  remote: "statuses.remote",
  pulling: "statuses.pulling",
  failed: "statuses.failed",
}

export { statusLabelKeys }

/* ── shared sub-components ──────────────────────────────── */

function ImageStatusBadge({ image, tImages }: { image: DockerImage; tImages: ImageTranslator }) {
  const StatusIcon = statusIcons[image.status]
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-xs-tight",
        image.status === "local" && "metadata-pill metadata-pill--source",
        image.status === "remote" && "metadata-pill",
        image.status === "pulling" && "bg-info/10 text-info border-info/20",
        image.status === "failed" && "bg-destructive/10 text-destructive border-destructive/20",
      )}
    >
      <StatusIcon
        className={cn(
          "h-3 w-3 mr-1",
          image.status === "pulling" && "animate-spin motion-reduce:animate-none"
        )}
      />
      {tImages(statusLabelKeys[image.status])}
    </Badge>
  )
}

function ImageActionsMenu({
  image,
  tImages,
  tCommon,
  onViewDetails,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
  triggerClassName,
  ariaLabel,
}: {
  image: DockerImage
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
  triggerClassName?: string
  ariaLabel?: string
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn("h-8 w-8", triggerClassName)}
          aria-label={ariaLabel ?? tCommon("actions")}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => onViewDetails(image)}>{tImages("actions.viewDetails")}</DropdownMenuItem>
        <DropdownMenuItem onClick={() => onCopyName(image)}>
          <Copy className="h-4 w-4 mr-2" />
          {tImages("actions.copyName")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => onCopyPullCommand(image)}>
          <Download className="h-4 w-4 mr-2" />
          {tImages("actions.copyPullCommand")}
        </DropdownMenuItem>
        {onDeleteLocal ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive" onClick={() => onDeleteLocal(image)}>
              {tImages("actions.deleteLocal")}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/* ── cards grid ─────────────────────────────────────────── */

export function ImageCardsGrid({
  images,
  tImages,
  tCommon,
  onPull,
  onViewDetails,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
}: {
  images: DockerImage[]
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
}) {
  const groups = buildImageRepositoryGroups(images)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {groups.map((group) => {
        const image = group.primaryImage
        return (
          <Card key={group.key} className="group relative overflow-hidden border-border/60 bg-card/92 hover:shadow-sm hover:border-border/90 transition-all duration-200 h-full flex flex-col">
            <article className="flex h-full flex-col">
            <CardContent className="p-4 flex-1 flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex min-w-0 w-full cursor-default items-center gap-2.5">
                        <div className="quiet-card-icon-shell quiet-card-icon-shell--artifact shrink-0">
                          <Package2 className="quiet-card-icon-glyph h-4 w-4" strokeWidth={1.8} />
                        </div>
                        <h2 className="min-w-0 truncate text-sm font-semibold text-foreground leading-tight">{group.label}</h2>
                      </div>
                    </TooltipTrigger>
                    {image.description && (
                      <TooltipContent side="right" className="max-w-xs">
                        {image.description}
                      </TooltipContent>
                    )}
                  </Tooltip>
                </div>
                <ImageActionsMenu
                  image={image}
                  tImages={tImages}
                  tCommon={tCommon}
                  onViewDetails={onViewDetails}
                  onCopyName={onCopyName}
                  onCopyPullCommand={onCopyPullCommand}
                  onDeleteLocal={onDeleteLocal}
                  triggerClassName="h-7 w-7 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100 shrink-0"
                />
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="secondary" className="text-xs-tight">
                  {tImages("card.versionCount", { count: group.images.length })}
                </Badge>
              </div>

              <div className="mt-3 grid gap-2">
                {group.images.map((version) => (
                  <ImageVersionRow
                    key={version.id}
                    image={version}
                    tImages={tImages}
                    tCommon={tCommon}
                    onPull={onPull}
                    onViewDetails={onViewDetails}
                    onCopyName={onCopyName}
                    onCopyPullCommand={onCopyPullCommand}
                    onDeleteLocal={onDeleteLocal}
                  />
                ))}
              </div>
            </CardContent>
            </article>
          </Card>
        )
      })}
    </div>
  )
}

function ImageVersionRow({
  image,
  tImages,
  tCommon,
  onPull,
  onViewDetails,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
}: {
  image: DockerImage
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
}) {
  return (
    <div
      className="grid gap-2 rounded-lg border border-border/55 bg-background/70 p-2"
      data-testid="image-version-row"
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <Badge variant="secondary" className="max-w-full text-xs-tight">
            <span className="truncate">{image.tag}</span>
          </Badge>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <HardDrive className="h-3 w-3" />
              {formatSize(image.size_bytes)}
            </span>
            <ImageStatusBadge image={image} tImages={tImages} />
          </div>
        </div>
        <ImageActionsMenu
          image={image}
          tImages={tImages}
          tCommon={tCommon}
          onViewDetails={onViewDetails}
          onCopyName={onCopyName}
          onCopyPullCommand={onCopyPullCommand}
          onDeleteLocal={onDeleteLocal}
          triggerClassName="h-7 w-7 shrink-0"
          ariaLabel={tImages("actions.versionActions", { tag: image.tag })}
        />
      </div>
      <Button
        className="h-8 w-full"
        size="sm"
        variant={image.status === "local" ? "outline" : "default"}
        disabled={image.status === "pulling"}
        onClick={() => onPull(image)}
      >
        <Download className="h-3.5 w-3.5 mr-2" />
        {image.status === "pulling"
          ? tImages("actions.pulling")
          : image.status === "local"
            ? tImages("actions.repull")
            : tImages("actions.pull")}
      </Button>
    </div>
  )
}

export function buildImageRepositoryGroups(images: DockerImage[]): ImageRepositoryGroup[] {
  const groups = new Map<string, DockerImage[]>()
  for (const image of images) {
    const key = getRepositoryKey(image)
    groups.set(key, [...(groups.get(key) ?? []), image])
  }
  return [...groups.entries()].map(([key, groupImages]) => {
    const sorted = sortImageVersions(groupImages)
    const primaryImage = pickPrimaryImage(sorted)
    return {
      key,
      label: primaryImage.name,
      registry: primaryImage.registry,
      images: sorted,
      primaryImage,
      status: getGroupStatus(sorted),
    }
  })
}

function getRepositoryKey(image: DockerImage) {
  const repository = stripTag(image.full_name) || image.name
  return `${image.registry || "docker.io"}:${repository}`
}

function stripTag(fullName: string) {
  const lastSlashIndex = fullName.lastIndexOf("/")
  const lastColonIndex = fullName.lastIndexOf(":")
  if (lastColonIndex > lastSlashIndex) return fullName.slice(0, lastColonIndex)
  return fullName
}

function sortImageVersions(images: DockerImage[]) {
  return [...images].sort((a, b) => {
    const statusOrder = statusRank(a.status) - statusRank(b.status)
    if (statusOrder !== 0) return statusOrder
    return a.tag.localeCompare(b.tag, undefined, { numeric: true, sensitivity: "base" })
  })
}

function pickPrimaryImage(images: DockerImage[]) {
  return images[0]
}

function getGroupStatus(images: DockerImage[]): ImageStatus {
  if (images.some((image) => image.status === "pulling")) return "pulling"
  if (images.some((image) => image.status === "local")) return "local"
  if (images.every((image) => image.status === "failed")) return "failed"
  return "remote"
}

function statusRank(status: ImageStatus) {
  switch (status) {
    case "pulling":
      return 0
    case "local":
      return 1
    case "remote":
      return 2
    case "failed":
      return 3
  }
}

/* ── table view ─────────────────────────────────────────── */

export function ImageTable({
  images,
  tImages,
  tCommon,
  onPull,
  onViewDetails,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
}: {
  images: DockerImage[]
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
}) {
  const columns: DataTableColumn<DockerImage>[] = [
    {
      key: "image",
      header: tImages("table.image"),
      cell: (image) => (
        <div>
          <p className="font-medium text-foreground text-sm">{image.name}</p>
          <p className="text-xs text-muted-foreground">{image.description || tImages("noDescription")}</p>
        </div>
      ),
    },
    {
      key: "version",
      header: tImages("table.version"),
      cell: (image) => <span className="text-sm text-muted-foreground">{image.tag}</span>,
    },
    {
      key: "size",
      header: tImages("table.size"),
      cell: (image) => <span className="text-sm text-muted-foreground">{formatSize(image.size_bytes)}</span>,
    },
    {
      key: "status",
      header: tImages("table.status"),
      cell: (image) => <ImageStatusBadge image={image} tImages={tImages} />,
    },
    {
      key: "actions",
      header: tImages("table.actions"),
      align: "right",
      cell: (image) => (
        <div className="flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={image.status === "pulling"}
            onClick={(e) => { e.stopPropagation(); onPull(image) }}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            {image.status === "pulling"
              ? tImages("actions.pulling")
              : image.status === "local"
                ? tImages("actions.repull")
                : tImages("actions.pull")}
          </Button>
          <ImageActionsMenu
            image={image}
            tImages={tImages}
            tCommon={tCommon}
            onViewDetails={onViewDetails}
            onCopyName={onCopyName}
            onCopyPullCommand={onCopyPullCommand}
            onDeleteLocal={onDeleteLocal}
          />
        </div>
      ),
    },
  ]

  return (
    <DataTable
      columns={columns}
      data={images}
      caption={tImages("tableCaption")}
      rowKey={(image) => image.id}
      className="overflow-x-auto"
    />
  )
}
