"use client"

import { useState } from "react"
import { ArrowRight, RotateCw } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"

function currentOrigin() {
  return typeof window === "undefined" ? "" : window.location.origin
}

export function resolveBrowserUrl(rawUrl: string, origin: string) {
  const trimmedUrl = rawUrl.trim()
  if (!trimmedUrl) return ""

  const parsed = parseBrowserUrl(trimmedUrl, origin)
  if (!parsed || (parsed.protocol !== "http:" && parsed.protocol !== "https:")) {
    return ""
  }
  return parsed.href
}

function parseBrowserUrl(rawUrl: string, origin: string) {
  const looksLikeHost = /^[\w-]+(\.[\w-]+)+(\/.*)?$/u.test(rawUrl)
  const looksLikeLocalHost =
    /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?([/?#].*)?$/iu.test(rawUrl)
  try {
    if (looksLikeLocalHost) return new URL(`http://${rawUrl}`)
    if (looksLikeHost) return new URL(`https://${rawUrl}`)
    if (origin) return new URL(rawUrl, origin)
    return new URL(rawUrl)
  } catch {
    return null
  }
}

type BrowserTabProps = {
  input?: string
  src?: string
  onInputChange?: (value: string) => void
  onSrcChange?: (value: string) => void
}

export function BrowserTab({
  input: controlledInput,
  src: controlledSrc,
  onInputChange,
  onSrcChange,
}: BrowserTabProps = {}) {
  const t = useTranslations("agentRuntime")
  const [origin] = useState(currentOrigin)
  const [internalInput, setInternalInput] = useState("")
  const [internalSrc, setInternalSrc] = useState("")
  const [reloadKey, setReloadKey] = useState(0)
  const input = controlledInput ?? internalInput
  const src = controlledSrc ?? internalSrc
  const setInput = onInputChange ?? setInternalInput
  const setSrc = onSrcChange ?? setInternalSrc

  const go = () => {
    const next = resolveBrowserUrl(input, origin)
    if (!next) return
    setSrc(next)
    setInput(next)
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" data-testid="browser-tab">
      <div className="flex items-center gap-1.5">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") go()
          }}
          placeholder={t("browser.urlPlaceholder")}
          className="min-w-0 flex-1 rounded-[8px] border border-border/70 bg-card px-3 py-1.5 text-xs text-foreground outline-none focus:border-border"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-[7px] text-muted-foreground"
          onClick={go}
          aria-label={t("browser.go")}
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-[7px] text-muted-foreground"
          onClick={() => setReloadKey((key) => key + 1)}
          aria-label={t("browser.reload")}
        >
          <RotateCw className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-[12px] border border-border/70 bg-card">
        {src ? (
          <iframe
            key={`${src}-${reloadKey}`}
            src={src}
            title={t("browser.title")}
            className="h-full w-full"
            sandbox="allow-same-origin allow-scripts allow-forms"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
            {t("browser.empty")}
          </div>
        )}
      </div>
    </div>
  )
}
