"use client"

import { memo } from "react"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type { TextPart as TextPartType } from "@/lib/chat-types"

interface TextPartProps {
  part: TextPartType
}

export const TextPart = memo(function TextPart({ part }: TextPartProps) {
  if (!part.text) return null

  return (
    <MarkdownRenderer
      content={part.text}
      className="
        break-words
        text-[15px]
        leading-relaxed
        [&_code]:text-[0.9em]
        [&_li]:leading-relaxed
        [&_ol]:my-3
        [&_p]:text-[15px]
        [&_p]:leading-relaxed
        [&_pre]:my-3
        [&_ul]:my-3
      "
    />
  )
})
