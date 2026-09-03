"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { ArrowLeft, ArrowRight, ExternalLink, Globe, RefreshCw } from "@/lib/icons"

export function resolveEmbeddedBrowserUrl(raw: string, origin: string) {
  const value = raw.trim()
  if (!value) return ""
  if (/\s/u.test(value)) return ""
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?([/?#].*)?$/iu.test(value)
  const host =
    /^(?:[\w-]+\.)+[\w-]+(?::\d{1,5})?(?:[/?#].*)?$/u.test(value)
  if (
    /^[a-z][a-z\d+.-]*:/iu.test(value) &&
    !/^https?:\/\//iu.test(value) &&
    !local &&
    !host
  ) {
    return ""
  }
  try {
    const url = local
      ? new URL(`http://${value}`)
      : host
        ? new URL(`https://${value}`)
        : new URL(value, origin)
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : ""
  } catch {
    return ""
  }
}

export function AgentBrowserPanel() {
  const t = useTranslations("workspace.browser")
  const origin = useMemo(() => (typeof window === "undefined" ? "http://localhost" : window.location.origin), [])
  const [input, setInput] = useState("")
  const [history, setHistory] = useState<string[]>([])
  const [index, setIndex] = useState(-1)
  const [reloadKey, setReloadKey] = useState(0)
  const src = history[index] ?? ""

  const navigate = (raw = input) => {
    const next = resolveEmbeddedBrowserUrl(raw, origin)
    if (!next) return
    const nextHistory = [...history.slice(0, index + 1), next]
    setHistory(nextHistory)
    setIndex(nextHistory.length - 1)
    setInput(next)
  }

  const move = (nextIndex: number) => {
    const next = history[nextIndex]
    if (!next) return
    setIndex(nextIndex)
    setInput(next)
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label={t("label")}>
      <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border/55 px-2">
        <Button type="button" variant="ghost" size="icon" className="size-8 rounded-md" disabled={index <= 0} onClick={() => move(index - 1)} aria-label={t("back")}>
          <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" variant="ghost" size="icon" className="size-8 rounded-md" disabled={index < 0 || index >= history.length - 1} onClick={() => move(index + 1)} aria-label={t("forward")}>
          <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" variant="ghost" size="icon" className="size-8 rounded-md" disabled={!src} onClick={() => setReloadKey((value) => value + 1)} aria-label={t("reload")}>
          <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        <label className="relative min-w-0 flex-1">
          <Globe aria-hidden="true" className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70" />
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") navigate()
            }}
            placeholder={t("placeholder")}
            aria-label={t("address")}
            className="h-8 w-full rounded-md border border-border/60 bg-muted/25 pl-7 pr-2 text-xs outline-none placeholder:text-muted-foreground/60 focus-visible:border-foreground/25 focus-visible:bg-background focus-visible:ring-2 focus-visible:ring-ring/20"
          />
        </label>
        <Button type="button" variant="ghost" size="icon" className="size-8 rounded-md" onClick={() => navigate()} aria-label={t("go")}>
          <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        {src ? (
          <Button variant="ghost" size="icon" className="size-8 rounded-md" asChild>
            <a href={src} target="_blank" rel="noreferrer" aria-label={t("openExternal")}>
              <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
            </a>
          </Button>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 bg-muted/10">
        {src ? (
          <iframe
            key={`${src}:${reloadKey}`}
            src={src}
            title={t("title")}
            className="h-full w-full border-0 bg-background"
            sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            {t("empty")}
          </div>
        )}
      </div>
    </section>
  )
}
