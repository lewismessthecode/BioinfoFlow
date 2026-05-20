"use client"

import type React from "react"
import { useRef, useEffect, useCallback, useState } from "react"
import { ArrowUp, Plus, Square, Upload } from "lucide-react"
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
  variant?: "home" | "thread"
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
  variant,
}: ChatInputProps) {
  const t = useTranslations("accessibility")
  const internalRef = useRef<HTMLTextAreaElement>(null)
  const textareaRef = externalRef ?? internalRef
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const dragCounterRef = useRef(0)
  const visualVariant = variant ?? (centered ? "home" : "thread")

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
  const canAttach = !disabled && Boolean(onFileDrop)

  const handleFileInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length > 0 && onFileDrop) {
      onFileDrop(files)
    }
    event.target.value = ""
  }, [onFileDrop])

  return (
    <div className={cn("mx-auto w-full", visualVariant === "home" ? "max-w-[720px]" : "max-w-3xl")}>
      <div
        className={cn(
          "group relative border bg-card transition-all duration-300 focus-within:border-foreground/30",
          visualVariant === "home"
            ? "rounded-[28px] px-2.5 py-1 shadow-[var(--composer-shadow)]"
            : "rounded-[24px] px-2.5 py-1 shadow-[0_2px_7px_rgba(60,64,67,0.08),0_12px_28px_rgba(60,64,67,0.10)]",
          isDragOver
            ? "border-primary border-dashed bg-primary/5 shadow-md"
            : "border-border/80 hover:border-foreground/20",
        )}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Drop overlay */}
        {isDragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-[28px] bg-primary/5 pointer-events-none">
            <div className="flex items-center gap-2 text-sm text-primary">
              <Upload className="h-4 w-4" />
              <span>Drop files to upload</span>
            </div>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="sr-only"
          tabIndex={-1}
          onChange={handleFileInputChange}
          disabled={!canAttach}
          aria-hidden="true"
        />

        <div className="flex min-h-10 items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 rounded-full text-foreground transition-colors hover:bg-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={!canAttach}
            aria-label={t("attachFiles")}
          >
            <Plus className="h-4 w-4" />
          </Button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? t("selectProject") : t("message")}
            aria-label={t("message")}
            className={cn(
              "min-w-0 flex-1 resize-none border-0 bg-transparent px-1 shadow-none outline-none selection:bg-primary/20 placeholder:text-muted-foreground/70 focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0",
              visualVariant === "home"
                ? "max-h-[164px] min-h-10 py-2.5 text-[14px] leading-5"
                : "max-h-[184px] min-h-10 py-2.5 text-[14px] leading-5",
            )}
            rows={1}
            disabled={disabled}
          />

          <div className="flex shrink-0 items-center gap-1">
            {modelSelector}
          </div>

          {isStreaming ? (
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0 rounded-full bg-secondary text-foreground transition-colors duration-200 hover:bg-secondary/80"
              onClick={onStop}
              aria-label={t("stopGenerating")}
            >
              <Square className="h-3.5 w-3.5 fill-current text-destructive" />
            </Button>
          ) : (
            <Button
              size="icon"
              className={cn(
                "h-8 w-8 min-h-8 min-w-8 shrink-0 rounded-full transition-colors duration-200",
                canSend
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80",
              )}
              onClick={onSend}
              disabled={!canSend}
              aria-label={t("sendMessage")}
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
          )}
        </div>

      </div>
    </div>
  )
}
