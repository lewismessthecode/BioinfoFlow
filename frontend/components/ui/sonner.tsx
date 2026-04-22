"use client"

import type React from "react"
import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"

const Toaster = ({ ...props }: ToasterProps) => {
  const { resolvedTheme } = useTheme()

  return (
    <Sonner
      theme={resolvedTheme as ToasterProps["theme"]}
      richColors
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--error-bg": "color-mix(in oklab, var(--destructive) 14%, white)",
          "--error-text": "color-mix(in oklab, var(--destructive) 88%, black)",
          "--error-border": "color-mix(in oklab, var(--destructive) 55%, white)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
