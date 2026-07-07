"use client"

import { useMemo, useState } from "react"
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
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { BrowseCard } from "@/components/bioinfoflow/card/browse-card"
import { cn } from "@/lib/utils"
import { formatSize } from "@/lib/format-utils"
import { canDeleteDockerImage } from "@/lib/docker-image-utils"
import type { DockerImage, ImageStatus } from "@/lib/types"

type ImageRepositoryGroup = {
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
        {onDeleteLocal && canDeleteDockerImage(image) ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive" onClick={() => onDeleteLocal(image)}>
              {tImages(image.status === "failed" ? "actions.deleteFailedRecord" : "actions.deleteLocal")}
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
  selectionMode = false,
  selectedImageIds,
  onToggleSelection,
}: {
  images: DockerImage[]
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
  selectionMode?: boolean
  selectedImageIds?: ReadonlySet<string>
  onToggleSelection?: (image: DockerImage) => void
}) {
  const groups = buildImageRepositoryGroups(images)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {groups.map((group) => (
        <ImageRepositoryCard
          key={group.key}
          group={group}
          tImages={tImages}
          tCommon={tCommon}
          onPull={onPull}
          onViewDetails={onViewDetails}
          onCopyName={onCopyName}
          onCopyPullCommand={onCopyPullCommand}
          onDeleteLocal={onDeleteLocal}
          selectionMode={selectionMode}
          selectedImageIds={selectedImageIds}
          onToggleSelection={onToggleSelection}
        />
      ))}
    </div>
  )
}

function ImageRepositoryCard({
  group,
  tImages,
  tCommon,
  onPull,
  onViewDetails,
  onCopyName,
  onCopyPullCommand,
  onDeleteLocal,
  selectionMode,
  selectedImageIds,
  onToggleSelection,
}: {
  group: ImageRepositoryGroup
  tImages: ImageTranslator
  tCommon: (key: string) => string
  onPull: (image: DockerImage) => void
  onViewDetails: (image: DockerImage) => void
  onCopyName: (image: DockerImage) => void
  onCopyPullCommand: (image: DockerImage) => void
  onDeleteLocal?: ((image: DockerImage) => void) | undefined
  selectionMode: boolean
  selectedImageIds?: ReadonlySet<string>
  onToggleSelection?: (image: DockerImage) => void
}) {
  const [selectedImageId, setSelectedImageId] = useState(group.primaryImage.id)
  const image = useMemo(
    () => group.images.find((item) => item.id === selectedImageId) ?? group.primaryImage,
    [group.images, group.primaryImage, selectedImageId],
  )
  const hasMultipleVersions = group.images.length > 1
  const isSelected = selectedImageIds?.has(image.id) ?? false
  const canSelect = selectionMode && image.status === "local" && Boolean(onToggleSelection)
  const handleVersionChange = (nextImageId: string) => {
    if (isSelected && nextImageId !== image.id) {
      onToggleSelection?.(image)
    }
    setSelectedImageId(nextImageId)
  }

  return (
    <article className="flex h-full flex-col">
      <BrowseCard
        title={group.label}
        icon={Package2}
        iconVariant="artifact"
        titleAs="h2"
        titleClassName="line-clamp-2 break-all"
        titleWrapper={(children) => (
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                className="cursor-default rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                tabIndex={0}
              >
                {children}
              </div>
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-xs">
              <div className="space-y-1">
                <p className="break-all font-mono text-xs">{image.full_name}</p>
                {image.description && <p>{image.description}</p>}
              </div>
            </TooltipContent>
          </Tooltip>
        )}
        menu={
          <div className="flex shrink-0 items-center gap-1">
            {canSelect ? (
              <label
                className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-border accent-foreground"
                  aria-label={tImages(isSelected ? "selection.unselectImage" : "selection.selectImage", {
                    name: image.name,
                    tag: image.tag,
                  })}
                  checked={isSelected}
                  onChange={() => onToggleSelection?.(image)}
                />
              </label>
            ) : null}
            <ImageActionsMenu
              image={image}
              tImages={tImages}
              tCommon={tCommon}
              onViewDetails={onViewDetails}
              onCopyName={onCopyName}
              onCopyPullCommand={onCopyPullCommand}
              onDeleteLocal={onDeleteLocal}
              triggerClassName="h-7 w-7 shrink-0 opacity-100"
              ariaLabel={tImages("actions.versionActions", { tag: image.tag })}
            />
          </div>
        }
        metadata={
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="metadata-pill text-xs-tight font-mono">
              {image.registry || "local"}
            </Badge>
            <ImageStatusBadge image={image} tImages={tImages} />
          </div>
        }
        footerMeta={
          <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
            <HardDrive className="h-3 w-3" />
            {formatSize(image.size_bytes)}
          </div>
        }
        actions={
          <>
            <Button
              className="w-full min-w-0"
              size="sm"
              variant={image.status === "local" ? "outline" : "default"}
              disabled={image.status === "pulling"}
              onClick={() => onPull(image)}
            >
              <Download className="h-3.5 w-3.5 mr-1.5 shrink-0" />
              <span className="truncate">
                {image.status === "pulling"
                  ? tImages("actions.pulling")
                  : image.status === "local"
                    ? tImages("actions.repull")
                    : tImages("actions.pull")}
              </span>
            </Button>
            <Button
              className="w-full min-w-0"
              size="sm"
              variant="outline"
              data-testid="image-card-view-details"
              onClick={() => onViewDetails(image)}
            >
              <span className="truncate">{tImages("actions.viewDetails")}</span>
            </Button>
          </>
        }
      >

          <div className="mt-3 flex items-center gap-2">
            {hasMultipleVersions ? (
              <Select value={image.id} onValueChange={handleVersionChange}>
                <SelectTrigger
                  className="h-8 min-w-0 flex-1 rounded-full bg-background text-xs"
                  aria-label={tImages("table.version")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {group.images.map((version) => (
                    <SelectItem key={version.id} value={version.id}>
                      {version.tag}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Badge variant="secondary" className="min-w-0 max-w-[65%] rounded-full px-3 py-1.5 text-xs-tight font-mono">
                <span className="truncate">{image.tag}</span>
              </Badge>
            )}
            <Badge variant="secondary" className="rounded-full px-2.5 text-xs-tight">
              {tImages("card.versionCount", { count: group.images.length })}
            </Badge>
          </div>
      </BrowseCard>
    </article>
  )
}

function buildImageRepositoryGroups(images: DockerImage[]): ImageRepositoryGroup[] {
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
