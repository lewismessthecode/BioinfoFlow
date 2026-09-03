"use client"

import { useEffect, useMemo, useState } from "react"
import { useTranslations } from "next-intl"

import { cn } from "@/lib/utils"

const highlightedCodeCache = new Map<string, string>()
let codeToHtmlPromise: Promise<typeof import("shiki").codeToHtml> | null = null

function getCodeToHtml() {
  codeToHtmlPromise ??= import("shiki").then((module) => module.codeToHtml)
  return codeToHtmlPromise
}

function languageForPath(path: string) {
  const extension = path.split(".").pop()?.toLowerCase()
  const languages: Record<string, string> = {
    bash: "bash",
    c: "c",
    cc: "cpp",
    conf: "ini",
    cpp: "cpp",
    css: "css",
    csv: "csv",
    env: "dotenv",
    fish: "fish",
    go: "go",
    h: "c",
    hpp: "cpp",
    html: "html",
    ini: "ini",
    java: "java",
    js: "javascript",
    json: "json",
    jsonl: "jsonl",
    jsx: "jsx",
    md: "markdown",
    mdx: "mdx",
    nf: "nextflow",
    py: "python",
    r: "r",
    rb: "ruby",
    rs: "rust",
    sh: "bash",
    sql: "sql",
    toml: "toml",
    ts: "typescript",
    tsv: "tsv",
    tsx: "tsx",
    txt: "text",
    wdl: "scala",
    xml: "xml",
    yaml: "yaml",
    yml: "yaml",
    zsh: "zsh",
  }
  return languages[extension ?? ""] ?? "text"
}

export function WorkspaceCodePreview({
  content,
  path,
  className,
}: {
  content: string
  path: string
  className?: string
}) {
  const language = languageForPath(path)
  const t = useTranslations("agentWorkbench.workspacePanel")
  const cacheKey = `${language}:${content}`
  const [highlightedState, setHighlightedState] = useState<{
    key: string
    html: string
  } | null>(null)
  const highlightedHtml =
    highlightedCodeCache.get(cacheKey) ??
    (highlightedState?.key === cacheKey ? highlightedState.html : null)
  const lineNumbers = useMemo(
    () => Array.from({ length: Math.max(1, content.split("\n").length) }, (_, index) => index + 1),
    [content],
  )

  useEffect(() => {
    let cancelled = false
    const cached = highlightedCodeCache.get(cacheKey)
    if (cached) return
    void getCodeToHtml()
      .then((codeToHtml) =>
        codeToHtml(content, {
          lang: language === "text" ? "txt" : language,
          themes: { light: "github-light", dark: "github-dark" },
        }),
      )
      .then((html) => {
        highlightedCodeCache.set(cacheKey, html)
        if (highlightedCodeCache.size > 100) {
          const first = highlightedCodeCache.keys().next().value
          if (first) highlightedCodeCache.delete(first)
        }
        if (!cancelled) setHighlightedState({ key: cacheKey, html })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [cacheKey, content, language])

  return (
    <div
      className={cn(
        "min-h-0 min-w-0 flex-1 overflow-auto bg-background font-mono text-[12px] leading-5",
        className,
      )}
      data-testid="workspace-code-preview"
      data-language={path.split(".").pop()?.toLowerCase() ?? "text"}
      data-highlight-language={language}
      aria-label={
        language === "scala" && path.toLowerCase().endsWith(".wdl")
          ? t("codePreview.wdlFallback")
          : undefined
      }
    >
      {language === "scala" && path.toLowerCase().endsWith(".wdl") ? (
        <span className="sr-only">{t("codePreview.wdlFallback")}</span>
      ) : null}
      <div className="flex min-h-full min-w-max items-stretch">
        <pre
          aria-hidden="true"
          className="sticky left-0 z-10 m-0 min-h-full select-none border-r border-border/45 bg-background px-3 py-2 text-right text-muted-foreground/65"
        >
          {lineNumbers.join("\n")}
        </pre>
        {highlightedHtml ? (
          <div
            className="markdown-code-highlight min-h-full [&_.shiki]:m-0 [&_.shiki]:min-h-full [&_.shiki]:min-w-max [&_.shiki]:bg-transparent! [&_.shiki]:px-4 [&_.shiki]:py-2 [&_.shiki]:font-mono [&_.shiki]:text-[12px] [&_.shiki]:leading-5"
            dangerouslySetInnerHTML={{ __html: highlightedHtml }}
          />
        ) : (
          <pre className="m-0 min-h-full min-w-max whitespace-pre px-4 py-2 text-foreground/88">
            {content}
          </pre>
        )}
      </div>
    </div>
  )
}
