import { describe, expect, it } from "vitest"

import {
  sanitizeSourceHref,
  sourcesFromActionResult,
} from "@/lib/agent-runtime/sources"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

function actionEvent(): AgentRuntimeEvent {
  return {
    id: "event-search",
    session_id: "session-1",
    turn_id: "turn-1",
    seq: 1,
    type: "action.completed",
    payload: {
      action_id: "action-search",
      name: "web.search",
    },
    visibility: "user",
    schema_version: 1,
    created_at: "2026-06-10T00:00:01Z",
    updated_at: "2026-06-10T00:00:01Z",
  }
}

describe("agent runtime source extraction", () => {
  it("classifies known source hosts using hostname boundaries", () => {
    const sources = sourcesFromActionResult(
      {
        results: [
          {
            title: "PubMed article",
            url: "https://pubmed.ncbi.nlm.nih.gov/23104886/",
          },
          {
            title: "NCBI docs",
            url: "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
          },
          {
            title: "bioRxiv FAQ",
            url: "https://www.biorxiv.org/about/FAQ",
          },
          {
            title: "GitHub source",
            url: "https://raw.githubusercontent.com/example/repo/main/README.md",
          },
        ],
      },
      actionEvent(),
    )

    expect(sources.map((source) => source.sourceType)).toEqual([
      "pubmed",
      "ncbi",
      "biorxiv",
      "github",
    ])
  })

  it("does not classify spoofed hosts by substring", () => {
    const sources = sourcesFromActionResult(
      {
        results: [
          {
            title: "Spoofed NCBI",
            url: "https://ncbi.nlm.nih.gov.attacker.example/result",
          },
          {
            title: "Spoofed bioRxiv",
            url: "https://biorxiv.org.attacker.example/about",
          },
          {
            title: "Spoofed GitHub",
            url: "https://github.com.attacker.example/repo",
          },
          {
            title: "Spoofed GitHubusercontent",
            url: "https://githubusercontent.com.attacker.example/file",
          },
        ],
      },
      actionEvent(),
    )

    expect(sources.map((source) => source.sourceType)).toEqual([
      "web",
      "web",
      "web",
      "web",
    ])
  })

  it("only makes normal web source URLs clickable", () => {
    expect(sanitizeSourceHref("https://pubmed.ncbi.nlm.nih.gov/23104886/")).toBe(
      "https://pubmed.ncbi.nlm.nih.gov/23104886/",
    )
    expect(sanitizeSourceHref("http://example.test/source")).toBe(
      "http://example.test/source",
    )
    expect(sanitizeSourceHref("javascript:alert(1)")).toBeUndefined()
    expect(sanitizeSourceHref("data:text/html,<script>alert(1)</script>")).toBeUndefined()
    expect(sanitizeSourceHref("/relative/source")).toBeUndefined()
  })

  it("uses action input preview as the query for backend-shaped search results", () => {
    const sources = sourcesFromActionResult(
      {
        results: [
          {
            title: "STAR search result",
            url: "https://pubmed.ncbi.nlm.nih.gov/23104886/",
          },
        ],
      },
      {
        ...actionEvent(),
        payload: {
          action_id: "action-search",
          name: "web.search",
          input_preview: "STAR RNA-seq aligner PubMed",
        },
      },
    )

    expect(sources[0]?.query).toBe("STAR RNA-seq aligner PubMed")
  })
})
