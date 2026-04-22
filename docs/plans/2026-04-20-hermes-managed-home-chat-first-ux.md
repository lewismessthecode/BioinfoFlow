# Hermes Managed Home And Chat-First UX

## Summary

This note captures the current Hermes integration shape after moving it to a
managed `BIOINFOFLOW_HOME/hermes` directory model. Bioinfoflow keeps its main
application database for product state, while Hermes owns the conversation
transcript, session artifacts, and SDK-local runtime files under one managed
home.

## Product Flow

```mermaid
flowchart LR
    User["User / Chat Page"] --> API["/agent API"]
    API --> Router["storage_backend routing"]
    Router --> Hermes["HermesConversationService"]
    Hermes --> AppDB["Bioinfoflow DB<br/>projects, runs, conversations,<br/>response handles, approval handles"]
    Hermes --> Registry["In-memory registry<br/>active task + cancel handle"]
    Hermes --> Runner["HermesRunner / AIAgent"]
    Runner --> Prompt["Hermes system prompt<br/>workflow -> validate -> submit -> explain"]
    Runner --> Tools["Hermes toolsets<br/>bioinfoflow tools + Hermes tools"]
    Tools --> Approval["Unified approval interrupt"]
    Runner --> SessionDB["Hermes SessionDB"]
    Runner --> Events["SSE events<br/>thinking / text / tool / approval"]
    Events --> User
    Approval --> Events
```

## Managed Home Layout

```mermaid
flowchart TB
    subgraph Managed["BIOINFOFLOW_HOME/hermes"]
        StateDB["state.db<br/>Hermes session index + searchable transcript"]
        Sessions["sessions/<br/>session json/jsonl artifacts"]
        Logs["logs/<br/>agent + SDK logs"]
        Cache["cache/<br/>SDK caches"]
        Memories["memories/<br/>Hermes local memory files"]
    end

    AppDB["Bioinfoflow main DB"]
    Runtime["Hermes runtime process"]

    Runtime --> Managed
    Runtime --> AppDB
```

## Chat-First UX

- Keep one assistant message per response.
- Append `thinking`, `tool-call`, `approval`, and final text into that same
  message thread.
- Treat risky tools like real interrupts: `submit_run` starts, pauses for
  approval, then resumes in place after approval.
- Use structured tool results so the chat UI can render concise previews instead
  of raw Python strings.
