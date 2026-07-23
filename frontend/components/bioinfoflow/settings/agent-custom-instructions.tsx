"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  AGENT_CUSTOM_INSTRUCTIONS_MAX_LENGTH,
  getAgentSettings,
  updateAgentSettings,
} from "@/lib/agent-settings"

type AgentCustomInstructionsLabels = {
  label: string
  description: string
  newSessionsOnly: string
  placeholder: string
  save: string
  saving: string
  clear: string
  saved: string
  saveFailed: string
  loadFailed: string
}

export function AgentCustomInstructions({
  labels,
}: {
  labels: AgentCustomInstructionsLabels
}) {
  const [instructions, setInstructions] = useState("")
  const [savedInstructions, setSavedInstructions] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<
    { kind: "success" | "error"; message: string } | undefined
  >()

  useEffect(() => {
    let active = true

    void getAgentSettings()
      .then((settings) => {
        if (!active) return
        setInstructions(settings.custom_instructions)
        setSavedInstructions(settings.custom_instructions)
      })
      .catch(() => {
        if (active) setStatus({ kind: "error", message: labels.loadFailed })
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [labels.loadFailed])

  const persist = async (nextInstructions: string) => {
    setSaving(true)
    setStatus(undefined)

    try {
      const settings = await updateAgentSettings(nextInstructions)
      setInstructions(settings.custom_instructions)
      setSavedInstructions(settings.custom_instructions)
      setStatus({ kind: "success", message: labels.saved })
    } catch {
      setStatus({ kind: "error", message: labels.saveFailed })
    } finally {
      setSaving(false)
    }
  }

  const disabled = loading || saving

  return (
    <div className="space-y-3 px-5 py-5 sm:px-6">
      <div className="space-y-1">
        <Label htmlFor="agent-custom-instructions">{labels.label}</Label>
        <p className="text-[13px] leading-5 text-muted-foreground">
          {labels.description}
        </p>
        <p className="text-[13px] font-medium leading-5 text-muted-foreground">
          {labels.newSessionsOnly}
        </p>
      </div>

      <Textarea
        id="agent-custom-instructions"
        value={instructions}
        onChange={(event) => {
          setInstructions(event.target.value)
          setStatus(undefined)
        }}
        placeholder={labels.placeholder}
        maxLength={AGENT_CUSTOM_INSTRUCTIONS_MAX_LENGTH}
        rows={9}
        disabled={disabled}
        className="min-h-44 resize-y"
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs tabular-nums text-muted-foreground">
          {instructions.length.toLocaleString()} /{" "}
          {AGENT_CUSTOM_INSTRUCTIONS_MAX_LENGTH.toLocaleString()}
        </span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled || !instructions}
            onClick={() => void persist("")}
          >
            {labels.clear}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={disabled || instructions === savedInstructions}
            onClick={() => void persist(instructions)}
          >
            {saving ? labels.saving : labels.save}
          </Button>
        </div>
      </div>

      {status ? (
        <p
          role={status.kind === "error" ? "alert" : "status"}
          className={
            status.kind === "error"
              ? "text-[13px] text-destructive"
              : "text-[13px] text-muted-foreground"
          }
        >
          {status.message}
        </p>
      ) : null}
    </div>
  )
}
