"use client"

import { useState } from "react"
import { ArrowRight, RotateCw } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"

function currentOrigin() {
  return typeof window === "undefined" ? "" : window.location.origin
}

export function BrowserTab() {
  const t = useTranslations("agentRuntime")
  const [origin] = useState(currentOrigin)
  const [input, setInput] = useState(currentOrigin)
  const [src, setSrc] = useState(currentOrigin)
  const [reloadKey, setReloadKey] = useState(0)

  const go = () => {
    const next = input.trim()
    if (!next) return
    // Same-origin only: embedding a cross-origin app is blocked by
    // X-Frame-Options, so we constrain the iframe to this deployment's origin.
    if (origin && !next.startsWith(origin)) {
      setSrc(origin)
      setInput(origin)
      return
    }
    setSrc(next)
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
          className="min-w-0 flex-1 rounded-full border border-border/70 bg-card px-3 py-1.5 text-xs text-foreground outline-none focus:border-border"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-full text-muted-foreground"
          onClick={go}
          aria-label={t("browser.go")}
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-full text-muted-foreground"
          onClick={() => setReloadKey((key) => key + 1)}
          aria-label={t("browser.reload")}
        >
          <RotateCw className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/70 bg-card">
        {src ? (
          <iframe
            key={`${src}-${reloadKey}`}
            src={src}
            title={t("browser.title")}
            className="h-full w-full"
            sandbox="allow-same-origin allow-scripts allow-forms"
          />
        ) : null}
      </div>
    </div>
  )
}
