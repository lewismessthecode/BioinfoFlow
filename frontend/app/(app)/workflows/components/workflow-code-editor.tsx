"use client"

import { forwardRef, useCallback, useEffect, useMemo, useRef, useImperativeHandle } from "react"
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror"
import { javascript } from "@codemirror/lang-javascript"
import {
  Decoration,
  type DecorationSet,
  EditorView,
} from "@codemirror/view"
import { type Extension, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state"
import { useTheme } from "next-themes"

interface ValidationError {
  line: number | null
  column: number | null
  message: string
  severity: string
}

interface WorkflowCodeEditorProps {
  content: string
  onChange: (content: string) => void
  errors?: ValidationError[]
  height?: string
  readOnly?: boolean
}

/* ── error-line decoration ─────────────────────────────── */

const setErrorLinesEffect = StateEffect.define<number[]>()

const errorLineField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },
  update(decorations, tr) {
    for (const e of tr.effects) {
      if (e.is(setErrorLinesEffect)) {
        const builder = new RangeSetBuilder<Decoration>()
        const doc = tr.state.doc
        const sorted = [...e.value].sort((a, b) => a - b)
        for (const lineNum of sorted) {
          if (lineNum >= 1 && lineNum <= doc.lines) {
            const line = doc.line(lineNum)
            builder.add(
              line.from,
              line.from,
              Decoration.line({ class: "cm-error-line" })
            )
          }
        }
        return builder.finish()
      }
    }
    return decorations
  },
  provide: (f) => EditorView.decorations.from(f),
})

/* ── theme ─────────────────────────────────────────────── */

const editorTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    borderRadius: "12px",
    overflow: "hidden",
  },
  "&.cm-focused": {
    outline: "none",
  },
  ".cm-error-line": {
    backgroundColor: "rgba(239, 68, 68, 0.08)",
    borderLeft: "3px solid rgb(239, 68, 68)",
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    borderRight: "1px solid var(--border)",
    color: "var(--muted-foreground)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "transparent",
  },
})

/* ── component ─────────────────────────────────────────── */

export const WorkflowCodeEditor = forwardRef<ReactCodeMirrorRef, WorkflowCodeEditorProps>(
  function WorkflowCodeEditor(
    { content, onChange, errors = [], height = "320px", readOnly = false },
    ref,
  ) {
    const internalRef = useRef<ReactCodeMirrorRef>(null)
    const { resolvedTheme } = useTheme()

    useImperativeHandle(ref, () => internalRef.current!, [])

    const extensions: Extension[] = useMemo(
      () => [javascript(), errorLineField, editorTheme, EditorView.lineWrapping],
      []
    )

    // Push error lines into the editor whenever errors change
    useEffect(() => {
      const view = internalRef.current?.view
      if (!view) return

      const errorLines = errors
        .filter((e): e is ValidationError & { line: number } => e.line !== null)
        .map((e) => e.line)

      view.dispatch({ effects: setErrorLinesEffect.of(errorLines) })
    }, [errors])

    const handleChange = useCallback(
      (value: string) => {
        onChange(value)
      },
      [onChange]
    )

    return (
      <div className="overflow-hidden rounded-xl border border-border/70 bg-background">
        <CodeMirror
          ref={internalRef}
          value={content}
          onChange={handleChange}
          extensions={extensions}
          height={height}
          readOnly={readOnly}
          theme={resolvedTheme === "dark" ? "dark" : "light"}
          basicSetup={{
            lineNumbers: true,
            highlightActiveLineGutter: true,
            highlightActiveLine: true,
            foldGutter: true,
            bracketMatching: true,
            closeBrackets: true,
            indentOnInput: true,
          }}
        />
      </div>
    )
  },
)

/* ── scroll-to-line helper (exported for parent use) ──── */

export function scrollEditorToLine(
  editorRef: React.RefObject<ReactCodeMirrorRef | null>,
  line: number
) {
  const view = editorRef.current?.view
  if (!view) return
  const lineInfo = view.state.doc.line(Math.min(line, view.state.doc.lines))
  view.dispatch({
    selection: { anchor: lineInfo.from },
    effects: EditorView.scrollIntoView(lineInfo.from, { y: "center" }),
  })
}
