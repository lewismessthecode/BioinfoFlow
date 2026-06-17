"use client"

import { useEffect, useMemo, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

interface MarkdownRendererProps {
  content: string
  className?: string
}

const highlightedCodeCache = new Map<string, string>()
const CACHE_MAX_SIZE = 200

// Singleton promise for the shiki codeToHtml function — avoids thundering herd
// when multiple CodeBlock instances mount simultaneously.
let shikiPromise: Promise<typeof import("shiki").codeToHtml> | null = null

function getCodeToHtml() {
  if (!shikiPromise) {
    shikiPromise = import("shiki").then((m) => m.codeToHtml)
  }
  return shikiPromise
}

function normalizeCodeLanguage(className?: string) {
  const match = /language-([\w-]+)/.exec(className || "")
  return match?.[1]?.toLowerCase() || "text"
}

function CodeBlock({
  code,
  language,
}: {
  code: string
  language: string
}) {
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null)
  const cacheKey = useMemo(() => `${language}::${code}`, [code, language])

  useEffect(() => {
    let cancelled = false

    const renderHighlightedCode = async () => {
      if (!code.trim()) {
        setHighlightedHtml(null)
        return
      }

      const cached = highlightedCodeCache.get(cacheKey)
      if (cached) {
        setHighlightedHtml(cached)
        return
      }

      try {
        const codeToHtml = await getCodeToHtml()
        const html = await codeToHtml(code, {
          lang: language === "text" ? "txt" : language,
          themes: {
            light: "github-light",
            dark: "github-dark",
          },
        })
        highlightedCodeCache.set(cacheKey, html)
        if (highlightedCodeCache.size > CACHE_MAX_SIZE) {
          // Evict oldest entry (first inserted key)
          const firstKey = highlightedCodeCache.keys().next().value
          if (firstKey) highlightedCodeCache.delete(firstKey)
        }
        if (!cancelled) {
          setHighlightedHtml(html)
        }
      } catch {
        if (!cancelled) {
          setHighlightedHtml(null)
        }
      }
    }

    void renderHighlightedCode()

    return () => {
      cancelled = true
    }
  }, [cacheKey, code, language])

  return (
    <div
      className="mb-3 min-w-0 max-w-full overflow-hidden rounded-xl border border-border/60 bg-secondary/60"
      data-testid="markdown-code-block"
    >
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
          {language}
        </span>
      </div>
      {highlightedHtml ? (
        <div
          className="min-w-0 max-w-full overflow-hidden [&_.shiki]:m-0 [&_.shiki]:max-w-full [&_.shiki]:overflow-x-auto [&_.shiki]:bg-transparent! [&_.shiki]:p-3 [&_.shiki_pre]:m-0"
          dangerouslySetInnerHTML={{ __html: highlightedHtml }}
        />
      ) : (
        <pre className="max-w-full overflow-x-auto p-3 text-sm-tight">
          <code className={`font-mono language-${language}`}>{code}</code>
        </pre>
      )}
    </div>
  )
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={cn("prose prose-sm dark:prose-invert min-w-0 max-w-none overflow-hidden break-words", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className="text-xl font-semibold text-foreground mt-4 mb-2 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold text-foreground mt-4 mb-2 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-semibold text-foreground mt-3 mb-1.5 first:mt-0">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-semibold text-foreground mt-2 mb-1 first:mt-0">{children}</h4>
          ),

          // Paragraphs
          p: ({ children }) => (
            <p className="text-sm leading-relaxed text-foreground mb-3 last:mb-0 break-words">{children}</p>
          ),

          // Lists
          ul: ({ children }) => (
            <ul className="list-disc list-outside ml-4 mb-3 space-y-1 text-sm">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-outside ml-4 mb-3 space-y-1 text-sm">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="text-foreground pl-1">{children}</li>
          ),

          // Inline code
          code: ({ className: codeClassName, children, ...props }) => {
            const language = normalizeCodeLanguage(codeClassName)
            const rawCode = String(children).replace(/\n$/, "")
            const isInline = !codeClassName
            if (isInline) {
              return (
                <code className="break-all rounded bg-secondary px-1.5 py-0.5 font-mono text-sm-tight text-foreground" {...props}>
                  {children}
                </code>
              )
            }
            return <CodeBlock code={rawCode} language={language} />
          },

          // Code blocks (pre)
          pre: ({ children }) => <>{children}</>,

          // Strong/Bold
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),

          // Emphasis/Italic
          em: ({ children }) => (
            <em className="italic text-foreground">{children}</em>
          ),

          // Links
          a: ({ href, children }) => {
            const sanitizedHref = (() => {
              if (!href) return undefined
              try {
                const url = new URL(href, "https://placeholder.invalid")
                if (["http:", "https:", "mailto:"].includes(url.protocol)) {
                  return href
                }
                return undefined
              } catch {
                return undefined
              }
            })()
            return (
              <a
                href={sanitizedHref}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {children}
              </a>
            )
          },

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary/50 pl-3 italic text-muted-foreground mb-3">
              {children}
            </blockquote>
          ),

          // Horizontal rule
          hr: () => <hr className="border-border my-4" />,

          // Tables
          table: ({ children }) => (
            <div
              className="mb-3 max-w-full overflow-x-auto"
              data-testid="markdown-table-scroller"
            >
              <table className="min-w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-secondary/50">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="border border-border px-3 py-1.5 text-left font-medium text-foreground">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-3 py-1.5 text-foreground">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
