"use client"

import {
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { Plus } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  createRemoteConnection,
  fetchRemoteConnections,
  runRemoteConnectionCommand,
  testRemoteConnection,
  updateRemoteConnection,
  type RemoteConnection,
  type RemoteConnectionCreateInput,
} from "@/lib/demo-connections"

import { ConnectionDetail } from "./components/connection-detail"
import {
  ConnectionDialog,
  initialConnectionForm,
  type ConnectionFormState,
  type DialogMode,
  type FormErrorField,
} from "./components/connection-dialog"
import { ConnectionList } from "./components/connection-list"

type UpsertConnectionOptions = {
  select?: boolean
}

function parsePort(value: string): number | null {
  const normalized = value.trim()
  if (!/^\d+$/.test(normalized)) return null
  const port = Number(normalized)
  return Number.isSafeInteger(port) && port >= 1 && port <= 65535 ? port : null
}

function formFromConnection(connection: RemoteConnection): ConnectionFormState {
  return {
    name: connection.name,
    host: connection.host,
    port: String(connection.port),
    username: connection.username,
    auth_method: connection.auth_method,
    ssh_alias: connection.ssh_alias,
    key_path: connection.key_path,
    skill_instructions: connection.skill_instructions,
  }
}

export default function ConnectionsPage() {
  const t = useTranslations("connections")
  const [connections, setConnections] = useState<RemoteConnection[]>([])
  const [selectedConnectionId, setSelectedConnectionId] = useState("")
  const [search, setSearch] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>("create")
  const [editingConnectionId, setEditingConnectionId] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionFormState>(initialConnectionForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [formErrorField, setFormErrorField] = useState<FormErrorField>(null)
  const [skillDragActive, setSkillDragActive] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isLoadingConnections, setIsLoadingConnections] = useState(true)
  const [connectionsLoadError, setConnectionsLoadError] = useState(false)
  const [testingConnectionId, setTestingConnectionId] = useState<string | null>(null)
  const [probeConnectionId, setProbeConnectionId] = useState<string | null>(null)
  const [probeOutputConnectionId, setProbeOutputConnectionId] = useState("")
  const [probeOutput, setProbeOutput] = useState("")
  const skillFileInputRef = useRef<HTMLInputElement>(null)
  const testRequestRef = useRef(0)
  const probeRequestRef = useRef(0)

  useEffect(() => {
    let disposed = false

    fetchRemoteConnections()
      .then((remoteConnections) => {
        if (disposed) return
        setConnections(remoteConnections)
        setConnectionsLoadError(false)
        setSelectedConnectionId((current) =>
          remoteConnections.some((connection) => connection.id === current)
            ? current
            : remoteConnections[0]?.id ?? "",
        )
      })
      .catch(() => {
        if (disposed) return
        setConnections([])
        setConnectionsLoadError(true)
        setSelectedConnectionId("")
      })
      .finally(() => {
        if (!disposed) setIsLoadingConnections(false)
      })

    return () => {
      disposed = true
    }
  }, [])

  const filteredConnections = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return connections

    return connections.filter((connection) =>
      [
        connection.name,
        connection.host,
        connection.username,
        connection.ssh_alias,
        connection.skill_instructions,
      ].some((value) => value.toLowerCase().includes(query)),
    )
  }, [connections, search])

  const selectedConnection =
    filteredConnections.find((connection) => connection.id === selectedConnectionId) ??
    filteredConnections[0] ??
    null

  const resetFormState = () => {
    setForm(initialConnectionForm)
    setFormError(null)
    setFormErrorField(null)
    setEditingConnectionId(null)
    setDialogMode("create")
    setSkillDragActive(false)
  }

  const handleDialogOpenChange = (open: boolean) => {
    setDialogOpen(open)
    if (!open) resetFormState()
  }

  const openCreateDialog = () => {
    resetFormState()
    setDialogMode("create")
    setDialogOpen(true)
  }

  const openEditDialog = (connection: RemoteConnection) => {
    setForm(formFromConnection(connection))
    setFormError(null)
    setFormErrorField(null)
    setDialogMode("edit")
    setEditingConnectionId(connection.id)
    setDialogOpen(true)
  }

  const buildPayload = (): RemoteConnectionCreateInput | null => {
    const host = form.host.trim()
    if (!host) {
      setFormError(t("form.errors.hostRequired"))
      setFormErrorField("host")
      return null
    }
    const name = form.name.trim() || host

    const port = parsePort(form.port)
    if (port === null) {
      setFormError(t("form.errors.invalidPort"))
      setFormErrorField("port")
      return null
    }

    const sshAlias = form.ssh_alias.trim()
    const keyPath = form.key_path.trim()
    if (form.auth_method === "ssh_config" && !sshAlias) {
      setFormError(t("form.errors.sshAliasRequired"))
      setFormErrorField("ssh_alias")
      return null
    }
    if (form.auth_method === "key_file" && !keyPath) {
      setFormError(t("form.errors.keyPathRequired"))
      setFormErrorField("key_path")
      return null
    }

    setFormError(null)
    setFormErrorField(null)
    return {
      name,
      host,
      port,
      username: form.username.trim() || t("form.defaultUsername"),
      auth_method: form.auth_method,
      ssh_alias: form.auth_method === "ssh_config" ? sshAlias : null,
      key_path: form.auth_method === "key_file" ? keyPath : null,
      skill_instructions: form.skill_instructions.trim() || null,
    }
  }

  const upsertConnection = (nextConnection: RemoteConnection, options: UpsertConnectionOptions = {}) => {
    setConnections((current) => {
      if (current.some((connection) => connection.id === nextConnection.id)) {
        return current.map((connection) =>
          connection.id === nextConnection.id ? nextConnection : connection,
        )
      }
      return [nextConnection, ...current]
    })
    setConnectionsLoadError(false)
    if (options.select ?? true) {
      setSelectedConnectionId(nextConnection.id)
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const payload = buildPayload()
    if (!payload) return

    setIsSaving(true)
    try {
      const nextConnection =
        dialogMode === "edit" && editingConnectionId
          ? await updateRemoteConnection(editingConnectionId, payload)
          : await createRemoteConnection(payload)

      upsertConnection(nextConnection)
      setDialogOpen(false)
      resetFormState()
      toast.success(
        dialogMode === "edit"
          ? t("toasts.connectionUpdated", { name: nextConnection.name })
          : t("toasts.connectionAdded", { name: nextConnection.name }),
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : t("form.errors.saveFailed")
      setFormError(message)
      setFormErrorField(null)
      toast.error(message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleTestConnection = async (connection: RemoteConnection) => {
    const requestId = testRequestRef.current + 1
    testRequestRef.current = requestId
    setTestingConnectionId(connection.id)
    try {
      const result = await testRemoteConnection(connection.id)
      if (testRequestRef.current !== requestId) return
      upsertConnection(result.connection, { select: false })
      if (result.status === "online") {
        toast.success(t("toasts.testSucceeded", { name: result.connection.name }))
      } else {
        toast.error(result.error || t("toasts.testFailed", { name: result.connection.name }))
      }
    } catch (error) {
      if (testRequestRef.current !== requestId) return
      const message = error instanceof Error ? error.message : t("toasts.testFailed", { name: connection.name })
      toast.error(message)
    } finally {
      if (testRequestRef.current === requestId) {
        setTestingConnectionId(null)
      }
    }
  }

  const handleRunProbe = async (connection: RemoteConnection) => {
    const requestId = probeRequestRef.current + 1
    probeRequestRef.current = requestId
    setProbeConnectionId(connection.id)
    setProbeOutputConnectionId(connection.id)
    setProbeOutput("")
    try {
      const result = await runRemoteConnectionCommand(connection.id, {
        command: "printf bioinfoflow-ok",
        timeout_seconds: 10,
        onFrame: (frame) => {
          if (probeRequestRef.current !== requestId) return
          if ((frame.type === "stdout" || frame.type === "stderr" || frame.type === "truncated") && frame.data) {
            setProbeOutput((current) => `${current}${frame.data}`)
          }
          if (frame.type === "error" && frame.message) {
            setProbeOutput((current) => `${current}${frame.message}\n`)
          }
        },
      })
      if (probeRequestRef.current === requestId) {
        setProbeOutput((current) => current || result.output || t("probe.emptyOutput"))
      }
    } catch (error) {
      if (probeRequestRef.current !== requestId) return
      const message = error instanceof Error ? error.message : t("probe.failed")
      setProbeOutput(message)
      toast.error(message)
    } finally {
      if (probeRequestRef.current === requestId) {
        setProbeConnectionId(null)
      }
    }
  }

  const appendSkillText = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setForm((current) => ({
      ...current,
      skill_instructions: current.skill_instructions.trim()
        ? `${current.skill_instructions.trim()}\n\n${trimmed}`
        : trimmed,
    }))
  }

  const importSkillFile = async (file?: File | null) => {
    if (!file) return
    try {
      appendSkillText(await file.text())
      toast.success(t("toasts.skillImported"))
    } catch {
      toast.error(t("form.errors.skillFileFailed"))
    }
  }

  const handleSkillDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setSkillDragActive(false)
    await importSkillFile(event.dataTransfer.files?.[0])
  }

  const handleSkillFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    await importSkillFile(event.target.files?.[0])
    event.target.value = ""
  }

  const selectedProbeOutput =
    selectedConnection && probeOutputConnectionId === selectedConnection.id ? probeOutput : ""

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:py-7">
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t("title")}</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Button className="h-9 w-fit rounded-full px-4 shadow-sm shadow-foreground/5" onClick={openCreateDialog}>
            <Plus className="h-4 w-4" />
            {t("addNode")}
          </Button>
        </div>

        <ConnectionDialog
          open={dialogOpen}
          mode={dialogMode}
          form={form}
          formError={formError}
          formErrorField={formErrorField}
          skillDragActive={skillDragActive}
          isSaving={isSaving}
          skillFileInputRef={skillFileInputRef}
          onOpenChange={handleDialogOpenChange}
          onSubmit={handleSubmit}
          onFormChange={setForm}
          onSkillDragActiveChange={setSkillDragActive}
          onSkillDrop={handleSkillDrop}
          onSkillFileChange={handleSkillFileChange}
          onAppendSkillText={appendSkillText}
        />

        <div className="grid overflow-hidden rounded-[28px] border border-border/60 bg-card/90 shadow-sm shadow-foreground/5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <ConnectionList
            connections={connections}
            filteredConnections={filteredConnections}
            selectedConnection={selectedConnection}
            search={search}
            isLoading={isLoadingConnections}
            loadError={connectionsLoadError}
            onSearchChange={setSearch}
            onSelectConnection={setSelectedConnectionId}
          />
          <ConnectionDetail
            connection={selectedConnection}
            hasConnections={connections.length > 0}
            testing={selectedConnection ? testingConnectionId === selectedConnection.id : false}
            probing={selectedConnection ? probeConnectionId === selectedConnection.id : false}
            probeOutput={selectedProbeOutput}
            onCreate={openCreateDialog}
            onClearSearch={() => setSearch("")}
            onEdit={openEditDialog}
            onTest={handleTestConnection}
            onRunProbe={handleRunProbe}
          />
        </div>
      </div>
    </div>
  )
}
