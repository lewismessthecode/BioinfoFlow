import {
  Check,
  Cloud,
  Loader2,
  AlertCircle,
  HardDrive,
  Download,
  Package,
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

function ImageStatusBadge({ image, tImages }: { image: DockerImage; tImages: (key: string) => string }) {
  const StatusIcon = statusIcons[image.status]
  return (
    <Badge
      variant="outline"
      className={cn(
        "text-xs-tight",
        image.status === "local" && "bg-success/10 text-success border-success/20",
        image.status === "remote" && "bg-muted text-muted-foreground",
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
}: {
  image: DockerImage
  tImages: (key: string) => string
  tCommon: (key: string) => string
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal: (image: DockerImage) => void
  triggerClassName?: string
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn("h-8 w-8", triggerClassName)}
          aria-label={tCommon("actions")}
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
        <DropdownMenuSeparator />
        <DropdownMenuItem className="text-destructive" onClick={() => onDeleteLocal(image)}>{tImages("actions.deleteLocal")}</DropdownMenuItem>
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
  tImages: (key: string) => string
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal: (image: DockerImage) => void
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {images.map((image) => {
        return (
          <Card key={image.id} className="group relative overflow-hidden border-border/60 bg-card/92 hover:shadow-sm hover:border-primary/20 transition-all duration-200 h-full flex flex-col">
            <CardContent className="p-4 flex-1 flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="flex items-center gap-2.5 min-w-0 cursor-default">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-secondary/50 dark:bg-secondary/30">
                        <Package className="h-3.5 w-3.5 text-foreground/70" />
                      </div>
                      <h2 className="text-sm font-semibold text-foreground leading-tight truncate">{image.name}</h2>
                    </div>
                  </TooltipTrigger>
                  {image.description && (
                    <TooltipContent side="right" className="max-w-xs">
                      {image.description}
                    </TooltipContent>
                  )}
                </Tooltip>
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

              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="secondary" className="text-xs-tight uppercase tracking-wide">
                  {image.tag}
                </Badge>
                <span className="flex items-center gap-1 text-muted-foreground">
                  <HardDrive className="h-3 w-3" />
                  {formatSize(image.size_bytes)}
                </span>
                <ImageStatusBadge image={image} tImages={tImages} />
              </div>

              <div className="mt-auto pt-1">
                <Button
                  className="w-full"
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
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
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
  tImages: (key: string) => string
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal: (image: DockerImage) => void
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
