"use client"

import type React from "react"
import { useRef, useEffect, useCallback, useState } from "react"
import { ArrowUp, Square, Upload } from "lucide-react"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface ChatInputProps {
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  onFileDrop?: (files: File[]) => void
  isStreaming: boolean
  disabled: boolean
  modelSelector?: React.ReactNode
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>
  centered?: boolean
}

export function ChatInput({
  input,
  onInputChange,
  onSend,
  onStop,
  onFileDrop,
  isStreaming,
  disabled,
  modelSelector,
  textareaRef: externalRef,
  centered,
}: ChatInputProps) {
  const t = useTranslations("accessibility")
  const internalRef = useRef<HTMLTextAreaElement>(null)
  const textareaRef = externalRef ?? internalRef
  const [isDragOver, setIsDragOver] = useState(false)
  const dragCounterRef = useRef(0)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input, textareaRef])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !disabled) onSend()
    }
  }

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current += 1
    if (e.dataTransfer.types.includes("Files")) {
      setIsDragOver(true)
    }
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDragOver(false)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setIsDragOver(false)

    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0 && onFileDrop) {
      onFileDrop(files)
    }
  }, [onFileDrop])

  const canSend = !disabled && input.trim().length > 0

  return (
    <div className={cn("mx-auto w-full", centered ? "max-w-2xl" : "max-w-3xl")}>
      <div
        className={cn(
          "group relative rounded-2xl border bg-card shadow-sm transition-all duration-300 focus-within:border-foreground/40",
          isDragOver
            ? "border-primary border-dashed bg-primary/5 shadow-md"
            : "border-border hover:border-foreground/30 hover:shadow-md",
          centered && "shadow-md",
        )}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Drop overlay */}
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-primary/5 pointer-events-none">
            <div className="flex items-center gap-2 text-sm text-primary">
              <Upload className="h-4 w-4" />
              <span>Drop files to upload</span>
            </div>
          </div>
        )}

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? t("selectProject") : t("message")}
          aria-label={t("message")}
          className={cn(
            "w-full resize-none border-0 bg-transparent shadow-none leading-relaxed outline-none focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/50 selection:bg-primary/20 max-h-[200px] px-5 py-3.5",
            centered ? "text-lg min-h-[64px]" : "text-base min-h-[52px]",
          )}
          rows={1}
          disabled={disabled}
        />

        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            {modelSelector}
          </div>

          <div className="flex items-center gap-2">
            {isStreaming ? (
              <Button
                size="icon"
                variant="ghost"
                className="h-9 w-9 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground transition-colors duration-200"
                onClick={onStop}
                aria-label={t("stopGenerating")}
              >
                <Square className="h-4 w-4 fill-current text-destructive" />
              </Button>
            ) : (
              <Button
                size="icon"
                className={`h-9 w-9 rounded-lg transition-colors duration-200 min-h-[36px] min-w-[36px] ${
                  canSend
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                }`}
                onClick={onSend}
                disabled={!canSend}
                aria-label={t("sendMessage")}
              >
                <ArrowUp className="h-5 w-5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
