"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface ResizeHandleProps {
  side: "left" | "right" | "top"
  onResize: (delta: number) => void
  onResizeEnd?: () => void
  className?: string
}

export function ResizeHandle({ side, onResize, onResizeEnd, className }: ResizeHandleProps) {
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)
  const startY = useRef(0)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    startX.current = e.clientX
    startY.current = e.clientY
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
    },
    [onResize, side]
  )

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
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

    const handleMouseUp = () => {
      setIsDragging(false)
      onResizeEnd?.()
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)

    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }
  }, [isDragging, onResize, onResizeEnd, side])

  return (
    <div
      className={cn(
        side === "top"
          ? "absolute left-0 right-0 top-0 h-1 cursor-row-resize z-10 group"
          : "absolute top-0 bottom-0 w-1 cursor-col-resize z-10 group",
        side === "left" ? "right-0" : side === "right" ? "left-0" : "",
        className
      )}
      onMouseDown={handleMouseDown}
      onKeyDown={handleKeyDown}
      role="separator"
      aria-orientation={side === "top" ? "horizontal" : "vertical"}
      aria-valuenow={50}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Resize ${side} sidebar`}
      tabIndex={0}
    >
      <div
        className={cn(
          side === "top"
            ? "absolute inset-x-0 top-0 h-1 transition-colors"
            : "absolute inset-y-0 w-1 transition-colors",
          side === "left" ? "right-0" : side === "right" ? "left-0" : "",
          isDragging
            ? "bg-primary"
            : "bg-transparent group-hover:bg-primary/50"
        )}
      />
    </div>
  )
}
