"use client"

import { useMemo, useState } from "react"
import { Avatar } from "@/components/ui/avatar"
import { useDevAvatarPreference } from "@/lib/avatar/avatar-preference"
import {
  findPixelPersona,
  parsePixelPersonaReference,
  resolveDefaultPixelPersona,
  type PixelPersona,
} from "@/lib/avatar/pixel-personas"
import { cn } from "@/lib/utils"

type UserAvatarProps = {
  viewerId?: string
  name: string
  image?: string | null
  authEnabled?: boolean
  alt?: string
  decorative?: boolean
  className?: string
  imageClassName?: string
  fallbackClassName?: string
}

function initialsFor(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "U"
}

export function PixelPersonaGraphic({
  persona,
  className,
}: {
  persona: PixelPersona
  className?: string
}) {
  const pixels = useMemo(
    () =>
      persona.pixels.flatMap((row, y) =>
        [...row].flatMap((token, x) => {
          if (token === ".") return []
          const fill = persona.palette[token]
          return fill ? [<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill={fill} />] : []
        }),
      ),
    [persona],
  )

  return (
    <svg
      viewBox="0 0 12 12"
      role="presentation"
      aria-hidden="true"
      data-testid={persona.key}
      className={cn("size-full", className)}
      shapeRendering="crispEdges"
    >
      <rect width="12" height="12" fill={persona.background} />
      {pixels}
    </svg>
  )
}

export function UserAvatar({
  viewerId,
  name,
  image,
  authEnabled = true,
  alt = "",
  decorative = false,
  className,
  imageClassName,
  fallbackClassName,
}: UserAvatarProps) {
  const devPreference = useDevAvatarPreference(!authEnabled)
  const effectiveImage = (!authEnabled && devPreference) || image || null
  const selectedKey = parsePixelPersonaReference(effectiveImage)
  const selectedPersona = selectedKey ? findPixelPersona(selectedKey) : null
  const defaultPersona = viewerId ? resolveDefaultPixelPersona(viewerId) : null
  const fallback = selectedPersona ?? defaultPersona
  const externalImage = effectiveImage && !selectedPersona ? effectiveImage : null
  const [failedImage, setFailedImage] = useState<string | null>(null)
  const showExternalImage = Boolean(externalImage && externalImage !== failedImage)
  const showPixelFallback = Boolean(selectedPersona || !showExternalImage)

  return (
    <Avatar
      className={cn("rounded-[8px]", className)}
      aria-hidden={decorative || undefined}
    >
      {showExternalImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- profile images may be authenticated blob URLs.
        <img
          src={externalImage ?? undefined}
          alt={decorative ? "" : alt}
          className={cn("size-full rounded-[8px] object-cover object-center", imageClassName)}
          onError={() => setFailedImage(externalImage)}
        />
      ) : null}
      {showPixelFallback ? (
        <span
          className={cn(
            "flex size-full items-center justify-center rounded-[8px] bg-primary/10 text-xs font-medium text-primary",
            fallbackClassName,
          )}
        >
          {fallback ? (
            <PixelPersonaGraphic persona={fallback} />
          ) : (
            initialsFor(name)
          )}
        </span>
      ) : null}
    </Avatar>
  )
}
