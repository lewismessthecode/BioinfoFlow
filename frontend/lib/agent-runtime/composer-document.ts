import type { AgentRuntimeInputPart } from "./types"

export type ComposerMention = {
  id: string
  kind: "file" | "directory" | "run" | "workflow"
  label: string
  detail?: string | null
  inputPart: AgentRuntimeInputPart
}

export type ComposerMentionRange = ComposerMention & {
  from: number
  to: number
}

export type ComposerDocument = {
  text: string
  mentions: ComposerMentionRange[]
}

export type ComposerDocumentChange = {
  from: number
  to: number
  insert: string
}

export const emptyComposerDocument = (): ComposerDocument => ({
  text: "",
  mentions: [],
})

export function insertComposerMention(
  document: ComposerDocument,
  mention: ComposerMention,
  from: number,
  to: number,
): ComposerDocument {
  if (document.mentions.some((item) => item.id === mention.id)) return document
  const safeFrom = clamp(from, 0, document.text.length)
  const safeTo = clamp(to, safeFrom, document.text.length)
  const displayText = `@${mention.label}`
  const changed = mapComposerDocumentChange(document, {
    from: safeFrom,
    to: safeTo,
    insert: displayText,
  })
  return {
    ...changed,
    mentions: [
      ...changed.mentions,
      { ...mention, from: safeFrom, to: safeFrom + displayText.length },
    ].sort((left, right) => left.from - right.from),
  }
}

export function removeComposerMentionAt(
  document: ComposerDocument,
  cursor: number,
): ComposerDocument {
  const mention = document.mentions.find(
    (item) => cursor > item.from && cursor <= item.to,
  )
  if (!mention) return document
  return mapComposerDocumentChange(document, {
    from: mention.from,
    to: mention.to,
    insert: "",
  })
}

export function mapComposerDocumentChange(
  document: ComposerDocument,
  change: ComposerDocumentChange,
): ComposerDocument {
  const from = clamp(change.from, 0, document.text.length)
  const to = clamp(change.to, from, document.text.length)
  const delta = change.insert.length - (to - from)
  return {
    text: `${document.text.slice(0, from)}${change.insert}${document.text.slice(to)}`,
    mentions: document.mentions.flatMap((mention) => {
      if (to <= mention.from) {
        return [{ ...mention, from: mention.from + delta, to: mention.to + delta }]
      }
      if (from >= mention.to) return [mention]
      return []
    }),
  }
}

export function composerDocumentReadableText(document: ComposerDocument): string {
  return document.text
}

export function composerDocumentInputParts(
  document: ComposerDocument,
): AgentRuntimeInputPart[] {
  const parts: AgentRuntimeInputPart[] = []
  let cursor = 0
  for (const mention of [...document.mentions].sort(
    (left, right) => left.from - right.from,
  )) {
    const text = document.text.slice(cursor, mention.from)
    if (text) parts.push({ type: "text", text })
    parts.push(mention.inputPart)
    cursor = mention.to
  }
  const trailingText = document.text.slice(cursor)
  if (trailingText) parts.push({ type: "text", text: trailingText })
  return parts
}

export function composerDocumentHasSendableContent(
  document: ComposerDocument,
): boolean {
  return document.text.trim().length > 0 || document.mentions.length > 0
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}
