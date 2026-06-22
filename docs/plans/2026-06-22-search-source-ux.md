# Search Source UX Plan

## Requirement

Bioinfoflow AI search must make evidence visible and verifiable. This matters
especially for bioinformatics work, where answers about papers, tools,
databases, pipeline parameters, or clinical-style interpretation cannot be
trusted unless users can inspect the source links behind the answer.

The target experience is not a plain answer with a hidden bibliography. Search
activity, source links, inline citations, and source previews should appear in
the agent reading flow, with a dedicated source panel for deeper review.

## Reference Designs

### Codex-Style Source Activity

The Codex screenshot highlights source evidence directly inside the conversation:

- Activity rows such as `已搜索网页` sit between answer paragraphs and show what
  the agent searched or edited.
- Source rows use recognizable icons such as globe, GitHub, or document icons.
- URLs are visible and clickable, with compact rows that can be collapsed.
- A small `来源` area groups several source icons near the message.
- Hovering a source reveals a preview card with the URL or title.

This pattern makes provenance feel like part of the work log. It is useful for
Bioinfoflow because agent actions, web searches, and research claims need to be
auditable without leaving the conversation.

### Grok-Style Source Drawer

The Grok screenshot highlights a separate source review surface:

- The answer includes inline source chips and a bottom `N sources` pill.
- Clicking the sources pill opens a right-side `Sources` drawer.
- The drawer lists thinking and search steps, including query text and result
  count badges.
- Inline citation hover shows a preview card with title, snippet, and source
  identity.
- The drawer can be closed and should preserve the reading context.

This pattern is useful for Bioinfoflow because users often need to audit many
queries and references after reading the answer.

## Bioinfoflow Design Direction

Bioinfoflow should combine the two patterns:

1. Show search activity rows in the agent transcript when web or literature
   search runs.
2. Show inline citations inside assistant answers for factual claims.
3. Show compact source chips and a bottom `N sources` control on source-backed
   answers.
4. Open a right-side `Sources` drawer on desktop and a bottom or full-screen
   sheet on mobile.
5. Show hover and keyboard-focus previews for every source chip.

The visual style should stay consistent with the current Bioinfoflow workbench:
quiet, dense, operational, and suited to repeated scientific review. It should
not become a marketing-style card layout.

## Source Model

The UI needs enough source metadata to support verification:

- `id`: stable source or citation identifier.
- `title`: human-readable page, paper, tool, or artifact title.
- `url`: original link.
- `domain`: short domain label.
- `snippet`: short evidence preview.
- `sourceType`: `web`, `pubmed`, `ncbi`, `biorxiv`, `github`, `docs`,
  `workflow`, or `artifact`.
- `query`: search query that found the source.
- `toolRunId`: tool or event id that produced the source.
- `citationId`: inline citation id used by answer text.
- `accessedAt`: optional timestamp for audit context.

Bioinformatics source types should prioritize PubMed, NCBI, bioRxiv, GitHub,
official tool documentation, and pipeline documentation.

## Acceptance Criteria

- A source-backed assistant answer shows inline citation chips near the claims
  they support.
- The answer footer shows an `N sources` pill when sources are present.
- Clicking an inline citation opens the source drawer and highlights the matching
  source.
- Clicking the footer sources pill opens the complete source drawer.
- Hovering or focusing a citation/source chip shows a preview card with title,
  domain, URL, source type, and snippet when available.
- Search activity appears as a collapsible transcript row with query, state,
  result count, and source chips.
- Loading, empty, and failed search states have explicit UI.
- User-facing copy exists in both English and Simplified Chinese locale files.
- Desktop uses a right-side drawer; narrow viewports use a bottom or full-screen
  sheet.
- Keyboard users can reach source chips, open/close the drawer, and return focus
  to the triggering control.

## Phases

1. Document the requirement and reference UX.
2. Add tested frontend source rendering primitives and sample transcript support.
3. Wire source controls into the agent workbench transcript and translations.
4. Run unit, lint, and visual checks.
5. Review with parallel agents, fix findings, and open a pull request.
