"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

type ResizePointerPosition = {
  clientX: number
  clientY: number
}

interface ResizeHandleProps {
  side: "left" | "right" | "top"
  onResize: (delta: number) => void
  onResizeStart?: (position: ResizePointerPosition) => void
  onResizeEnd?: () => void
  onResizePointer?: (position: ResizePointerPosition) => void
  className?: string
  ariaLabel?: string
  valueNow?: number
  valueMin?: number
  valueMax?: number
}

export function ResizeHandle({
  side,
  onResize,
  onResizeStart,
  onResizeEnd,
  onResizePointer,
  className,
  ariaLabel,
  valueNow,
  valueMin,
  valueMax,
}: ResizeHandleProps) {
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)
  const startY = useRef(0)

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.currentTarget.setPointerCapture?.(event.pointerId)
      setIsDragging(true)
      startX.current = event.clientX
      startY.current = event.clientY
      onResizeStart?.({ clientX: event.clientX, clientY: event.clientY })
    },
    [onResizeStart],
  )

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
    },
    [onResize, side]
  )

  useEffect(() => {
    if (!isDragging) return

    const originalUserSelect = document.body.style.userSelect
    document.body.style.userSelect = "none"

    const handlePointerMove = (event: PointerEvent) => {
      if (onResizePointer) {
        onResizePointer({ clientX: event.clientX, clientY: event.clientY })
        return
      }
      let delta = 0
      if (side === "top") {
        delta = startY.current - event.clientY
        startY.current = event.clientY
      } else {
        delta = side === "left"
          ? event.clientX - startX.current
          : startX.current - event.clientX
        startX.current = event.clientX
      }
      onResize(delta)
    }

    const finishResize = () => {
      setIsDragging(false)
      onResizeEnd?.()
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", finishResize, { once: true })
    window.addEventListener("pointercancel", finishResize, { once: true })
    window.addEventListener("blur", finishResize, { once: true })

    return () => {
      document.body.style.userSelect = originalUserSelect
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", finishResize)
      window.removeEventListener("pointercancel", finishResize)
      window.removeEventListener("blur", finishResize)
    }
  }, [isDragging, onResize, onResizeEnd, onResizePointer, side])

  return (
    <div
      className={cn(
        side === "top"
          ? "absolute left-0 right-0 top-0 z-10 h-2 cursor-row-resize touch-none group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
          : "absolute top-0 bottom-0 z-10 w-2 cursor-col-resize touch-none group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
        side === "left" ? "right-0" : side === "right" ? "left-0" : "",
        className
      )}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      role="separator"
      aria-orientation={side === "top" ? "horizontal" : "vertical"}
      aria-valuenow={valueNow}
      aria-valuemin={valueNow === undefined ? undefined : valueMin}
      aria-valuemax={valueNow === undefined ? undefined : valueMax}
      aria-label={ariaLabel ?? `Resize ${side} sidebar`}
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
