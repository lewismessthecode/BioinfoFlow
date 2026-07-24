import { describe, expect, it } from "vitest"

import {
  composerDocumentInputParts,
  composerDocumentReadableText,
  insertComposerMention,
  mapComposerDocumentChange,
  removeComposerMentionAt,
  type ComposerDocument,
} from "@/lib/agent-runtime/composer-document"

const fileMention = {
  id: "file:attachment-1",
  kind: "file" as const,
  label: "samples.csv",
  detail: "Uploaded file",
  inputPart: { type: "file_ref" as const, attachment_id: "attachment-1" },
}

describe("composer document", () => {
  it("inserts mentions at the cursor and preserves ordered ranges", () => {
    const document = insertComposerMention(
      { text: "Review  please", mentions: [] },
      fileMention,
      7,
      7,
    )

    expect(document.text).toBe("Review @samples.csv please")
    expect(document.mentions).toEqual([
      expect.objectContaining({ id: fileMention.id, from: 7, to: 19 }),
    ])
  })

  it("prevents duplicate structured references", () => {
    const once = insertComposerMention({ text: "", mentions: [] }, fileMention, 0, 0)
    expect(insertComposerMention(once, fileMention, once.text.length, once.text.length)).toEqual(once)
  })

  it("serializes readable clipboard text and model input parts", () => {
    const document = insertComposerMention(
      { text: "Review ", mentions: [] },
      fileMention,
      7,
      7,
    )

    expect(composerDocumentReadableText(document)).toBe("Review @samples.csv")
    expect(composerDocumentInputParts(document)).toEqual([
      { type: "text", text: "Review " },
      { type: "file_ref", attachment_id: "attachment-1" },
    ])
  })

  it("deletes a whole mention when backspace touches its trailing edge", () => {
    const document = insertComposerMention({ text: "Use ", mentions: [] }, fileMention, 4, 4)
    expect(removeComposerMentionAt(document, document.text.length)).toEqual({
      text: "Use ",
      mentions: [],
    })
  })

  it("maps mention ranges after text insertion before a token", () => {
    const initial = insertComposerMention({ text: "Use ", mentions: [] }, fileMention, 4, 4)
    const changed = mapComposerDocumentChange(initial, {
      from: 0,
      to: 0,
      insert: "Please ",
    })

    expect(changed.text).toBe("Please Use @samples.csv")
    expect(changed.mentions[0]).toMatchObject({ from: 11, to: 23 })
  })

  it("drops mention metadata when a change overlaps the token", () => {
    const initial: ComposerDocument = insertComposerMention(
      { text: "Use ", mentions: [] },
      fileMention,
      4,
      4,
    )
    const changed = mapComposerDocumentChange(initial, {
      from: 6,
      to: 8,
      insert: "",
    })

    expect(changed.mentions).toEqual([])
  })
})
