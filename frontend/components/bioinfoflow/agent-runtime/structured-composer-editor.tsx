"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { EditorState, RangeSet, StateEffect, StateField } from "@codemirror/state"
import { Decoration, EditorView, keymap } from "@codemirror/view"

import type {
  AgentRuntimeContextSearchItem,
  AgentRuntimeContextSearchResponse,
  ComposerDocument,
  ComposerMention,
  ComposerMentionRange,
} from "@/lib/agent-runtime"
import {
  composerDocumentReadableText,
  insertComposerMention,
  mapComposerDocumentChange,
  removeComposerMentionAt,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ContextPickerMenu } from "./context-picker-menu"

type StructuredComposerEditorProps = {
  value: ComposerDocument
  onChange: (value: ComposerDocument) => void
  onSubmit?: () => void
  onSearch?: (
    query: string,
    options?: { signal?: AbortSignal },
  ) => Promise<AgentRuntimeContextSearchResponse>
  disabled?: boolean
  ariaLabel: string
  placeholder?: string
  className?: string
}

const setMentionRanges = StateEffect.define<ComposerMentionRange[]>()

const mentionDecorations = StateField.define<RangeSet<Decoration>>({
  create: () => Decoration.none,
  update: (decorations, transaction) => {
    let next = decorations.map(transaction.changes)
    for (const effect of transaction.effects) {
      if (effect.is(setMentionRanges)) {
        next = Decoration.set(
          effect.value.map((mention) =>
            Decoration.mark({
              class: `agent-composer-mention agent-composer-mention-${mention.kind}`,
              attributes: { "data-mention-id": mention.id },
            }).range(mention.from, mention.to),
          ),
          true,
        )
      }
    }
    return next
  },
  provide: (field) => [
    EditorView.decorations.from(field),
    EditorView.atomicRanges.of((view) => view.state.field(field)),
  ],
})

type ActiveQuery = { from: number; to: number; query: string }

export function StructuredComposerEditor({
  value,
  onChange,
  onSubmit,
  onSearch,
  disabled = false,
  ariaLabel,
  placeholder,
  className,
}: StructuredComposerEditorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const viewRef = useRef<EditorView | null>(null)
  const valueRef = useRef(value)
  const onChangeRef = useRef(onChange)
  const onSubmitRef = useRef(onSubmit)
  const composingRef = useRef(false)
  const syncingRef = useRef(false)
  const queryRef = useRef<ActiveQuery | null>(null)
  const resultsRef = useRef<AgentRuntimeContextSearchItem[]>([])
  const highlightedIndexRef = useRef(0)
  const [query, setQuery] = useState<ActiveQuery | null>(null)
  const [results, setResults] = useState<AgentRuntimeContextSearchItem[]>([])
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "empty" | "error">("idle")
  const [error, setError] = useState<string | null>(null)
  const [highlightedIndex, setHighlightedIndex] = useState(0)

  useEffect(() => {
    valueRef.current = value
    onChangeRef.current = onChange
    onSubmitRef.current = onSubmit
    queryRef.current = query
    resultsRef.current = results
    highlightedIndexRef.current = highlightedIndex
  }, [highlightedIndex, onChange, onSubmit, query, results, value])

  const closePicker = useCallback(() => {
    setQuery(null)
    setResults([])
    setStatus("idle")
    setError(null)
    setHighlightedIndex(0)
  }, [])

  const selectResult = useCallback(
    (item: AgentRuntimeContextSearchItem) => {
      const view = viewRef.current
      const active = view
        ? activeQueryAt(
            valueRef.current.text,
            view.state.selection.main.head,
            valueRef.current.mentions,
          )
        : null
      if (!active || !view) return
      const mention: ComposerMention = {
        id: item.id,
        kind: item.kind,
        label: item.label,
        detail: item.detail,
        inputPart: item.input_part,
      }
      const next = insertComposerMention(
        valueRef.current,
        mention,
        active.from,
        active.to,
      )
      const withSpace = mapComposerDocumentChange(next, {
        from: active.from + item.label.length + 1,
        to: active.from + item.label.length + 1,
        insert: " ",
      })
      onChangeRef.current(withSpace)
      closePicker()
    },
    [closePicker],
  )

  useEffect(() => {
    if (!hostRef.current) return
    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: valueRef.current.text,
        selection: { anchor: valueRef.current.text.length },
        extensions: [
          mentionDecorations,
          EditorView.lineWrapping,
          EditorState.readOnly.of(disabled),
          EditorView.contentAttributes.of({
            role: "textbox",
            "aria-label": ariaLabel,
            "aria-multiline": "true",
            ...(placeholder ? { "data-placeholder": placeholder } : {}),
          }),
          EditorView.theme({
            "&": { backgroundColor: "transparent" },
            ".cm-scroller": { fontFamily: "inherit", overflow: "auto" },
            ".cm-content": { padding: "0", minHeight: "24px", caretColor: "currentColor" },
            ".cm-line": { padding: "0" },
            ".cm-focused": { outline: "none" },
            ".cm-gutters": { display: "none" },
            ".agent-composer-mention": {
              borderRadius: "4px",
              padding: "1px 3px",
              backgroundColor: "color-mix(in srgb, var(--accent) 82%, transparent)",
              color: "var(--accent-foreground)",
            },
          }),
          EditorView.domEventHandlers({
            compositionstart: () => {
              composingRef.current = true
              return false
            },
            compositionend: () => {
              composingRef.current = false
              return false
            },
            copy: (event) => {
              event.clipboardData?.setData(
                "text/plain",
                composerDocumentReadableText(valueRef.current),
              )
              event.preventDefault()
              return true
            },
            keydown: (event, currentView) => {
              if (event.key !== "Backspace") return false
              const selection = currentView.state.selection.main
              if (!selection.empty) return false
              const next = removeComposerMentionAt(valueRef.current, selection.head)
              if (next === valueRef.current) return false
              event.preventDefault()
              onChangeRef.current(next)
              return true
            },
          }),
          keymap.of([
            {
              key: "ArrowDown",
              run: () => {
                if (!queryRef.current || !resultsRef.current.length) return false
                setHighlightedIndex(
                  (index) => (index + 1) % resultsRef.current.length,
                )
                return true
              },
            },
            {
              key: "ArrowUp",
              run: () => {
                if (!queryRef.current || !resultsRef.current.length) return false
                setHighlightedIndex(
                  (index) =>
                    (index - 1 + resultsRef.current.length) %
                    resultsRef.current.length,
                )
                return true
              },
            },
            {
              key: "Tab",
              run: () => {
                if (!queryRef.current || !resultsRef.current.length) return false
                selectResult(
                  resultsRef.current[highlightedIndexRef.current] ??
                    resultsRef.current[0],
                )
                return true
              },
            },
            {
              key: "Escape",
              run: () => {
                if (!queryRef.current) return false
                closePicker()
                return true
              },
            },
            {
              key: "Enter",
              run: () => {
                if (composingRef.current) return true
                if (queryRef.current && resultsRef.current.length) {
                  selectResult(
                    resultsRef.current[highlightedIndexRef.current] ??
                      resultsRef.current[0],
                  )
                  return true
                }
                onSubmitRef.current?.()
                return Boolean(onSubmitRef.current)
              },
            },
            {
              key: "Shift-Enter",
              run: () => false,
            },
          ]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged || syncingRef.current) return
            let next = valueRef.current
            update.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
              next = mapComposerDocumentChange(next, {
                from: fromA,
                to: toA,
                insert: inserted.toString(),
              })
            })
            valueRef.current = next
            onChangeRef.current(next)
            const cursor = update.state.selection.main.head
            const active = activeQueryAt(next.text, cursor, next.mentions)
            setQuery(active)
            setHighlightedIndex(0)
            setResults([])
            setStatus(active ? (onSearch ? "loading" : "empty") : "idle")
          }),
        ],
      }),
    })
    view.dispatch({ effects: setMentionRanges.of(valueRef.current.mentions) })
    view.dispatch({ selection: { anchor: valueRef.current.text.length } })
    viewRef.current = view
    return () => {
      viewRef.current = null
      view.destroy()
    }
  }, [ariaLabel, closePicker, disabled, onSearch, placeholder, selectResult])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    if (view.state.doc.toString() !== value.text) {
      syncingRef.current = true
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value.text },
        selection: { anchor: value.text.length },
        effects: setMentionRanges.of(value.mentions),
      })
      syncingRef.current = false
    } else {
      view.dispatch({ effects: setMentionRanges.of(value.mentions) })
    }
  }, [value])

  useEffect(() => {
    if (!query || !onSearch) return
    const controller = new AbortController()
    const timeout = window.setTimeout(() => {
      setError(null)
      void onSearch(query.query, { signal: controller.signal })
        .then((response) => {
          if (controller.signal.aborted) return
          setResults(response.results)
          setStatus(response.results.length ? "ready" : "empty")
        })
        .catch((caught: unknown) => {
          if (controller.signal.aborted) return
          setResults([])
          setError(caught instanceof Error ? caught.message : "Context search failed")
          setStatus("error")
        })
    }, 150)
    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [onSearch, query])

  return (
    <div className={cn("relative min-w-0", className)}>
      <div
        ref={hostRef}
        onKeyDownCapture={(event) => {
          if (event.key !== "Backspace") return
          const view = viewRef.current
          if (!view) return
          const selection = view.state.selection.main
          if (!selection.empty) return
          const next = removeComposerMentionAt(valueRef.current, selection.head)
          if (next === valueRef.current) return
          event.preventDefault()
          event.stopPropagation()
          onChangeRef.current(next)
        }}
      />
      <ContextPickerMenu
        open={Boolean(query)}
        status={status}
        results={results}
        error={error}
        highlightedIndex={highlightedIndex}
        onSelect={selectResult}
      />
    </div>
  )
}

function activeQueryAt(
  text: string,
  cursor: number,
  mentions: ComposerMentionRange[],
): ActiveQuery | null {
  if (mentions.some((mention) => cursor > mention.from && cursor <= mention.to)) {
    return null
  }
  const prefix = text.slice(0, cursor)
  const match = prefix.match(/(?:^|\s)@([^\s@]*)$/)
  if (!match) return null
  const from = cursor - match[1].length - 1
  return { from, to: cursor, query: match[1] }
}
