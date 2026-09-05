"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface ResizeHandleProps {
  side: "left" | "right" | "top"
  onResize: (delta: number) => void
  onResizeEnd?: () => void
  className?: string
  ariaLabel?: string
  valueNow?: number
  valueMin?: number
  valueMax?: number
}

export function ResizeHandle({
  side,
  onResize,
  onResizeEnd,
  className,
  ariaLabel,
  valueNow,
  valueMin,
  valueMax,
}: ResizeHandleProps) {
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)
  const startY = useRef(0)
  const pointerId = useRef<number | null>(null)

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    pointerId.current = e.pointerId
    setIsDragging(true)
    startX.current = e.clientX
    startY.current = e.clientY
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }, [])

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const supportedKeys =
        side === "top"
          ? ["ArrowUp", "ArrowDown"]
          : ["ArrowLeft", "ArrowRight"]
      if (!supportedKeys.includes(event.key)) return
      event.preventDefault()
      const step = event.shiftKey ? 40 : 16
      let delta = 0
      if (side === "top") {
        delta = event.key === "ArrowUp" ? step : -step
      } else {
        const direction = side === "left" ? 1 : -1
        delta = event.key === "ArrowRight" ? step * direction : -step * direction
      }
      onResize(delta)
      onResizeEnd?.()
    },
    [onResize, onResizeEnd, side]
  )

  useEffect(() => {
    if (!isDragging) return

    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = side === "top" ? "row-resize" : "col-resize"
    document.body.style.userSelect = "none"

    const handlePointerMove = (e: PointerEvent) => {
      if (pointerId.current !== null && e.pointerId !== pointerId.current) return
      let delta = 0
      if (side === "top") {
        delta = startY.current - e.clientY
        startY.current = e.clientY
      } else {
        delta = side === "left"
          ? e.clientX - startX.current
          : startX.current - e.clientX
        startX.current = e.clientX
      }
      onResize(delta)
    }

    const finishDrag = () => {
      setIsDragging(false)
      pointerId.current = null
      onResizeEnd?.()
    }

    document.addEventListener("pointermove", handlePointerMove)
    document.addEventListener("pointerup", finishDrag)
    document.addEventListener("pointercancel", finishDrag)

    return () => {
      document.removeEventListener("pointermove", handlePointerMove)
      document.removeEventListener("pointerup", finishDrag)
      document.removeEventListener("pointercancel", finishDrag)
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }
  }, [isDragging, onResize, onResizeEnd, side])

  return (
    <div
      className={cn(
        side === "top"
          ? "absolute left-0 right-0 top-0 z-10 h-2 cursor-row-resize group"
          : "absolute top-0 bottom-0 z-10 w-2 cursor-col-resize group",
        side === "left" ? "right-0" : side === "right" ? "left-0" : "",
        "rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/70 focus-visible:ring-offset-1",
        className
      )}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      role="separator"
      aria-orientation={side === "top" ? "horizontal" : "vertical"}
      aria-valuenow={valueNow}
      aria-valuemin={valueNow === undefined ? undefined : valueMin}
      aria-valuemax={valueNow === undefined ? undefined : valueMax}
      aria-label={ariaLabel}
      tabIndex={0}
    >
      <div
        className={cn(
          side === "top"
            ? "absolute inset-x-0 top-0 h-px transition-colors"
            : "absolute inset-y-0 w-px transition-colors",
          side === "left" ? "right-0" : side === "right" ? "left-0" : "",
          isDragging
            ? "bg-primary"
            : "bg-transparent group-hover:bg-primary/50"
        )}
      />
    </div>
  )
}
