"use client"

import {
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import {
  createRemoteConnection,
  deleteRemoteConnection,
  fetchRemoteConnections,
  runRemoteConnectionCommand,
  testRemoteConnection,
  updateRemoteConnection,
  type RemoteConnection,
  type RemoteConnectionAuthMethod,
  type RemoteConnectionCreateInput,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

import {
  ConnectionDialog,
  initialConnectionForm,
  type ConnectionFormState,
  type DialogMode,
  type FormErrorField,
} from "./components/connection-dialog"
import { ConnectionList, type ConnectionStatusFilter } from "./components/connection-list"

type UpsertConnectionOptions = {
  select?: boolean
}

type Translate = (key: string, values?: Record<string, string | number>) => string

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
    password: "",
    private_key: "",
    passphrase: "",
    skill_instructions: connection.skill_instructions,
  }
}

export default function ConnectionsPage() {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")
  const [connections, setConnections] = useState<RemoteConnection[]>([])
  const [selectedConnectionId, setSelectedConnectionId] = useState("")
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<ConnectionStatusFilter>("all")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>("create")
  const [editingConnectionId, setEditingConnectionId] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionFormState>(initialConnectionForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [formErrorField, setFormErrorField] = useState<FormErrorField>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isLoadingConnections, setIsLoadingConnections] = useState(true)
  const [connectionsLoadError, setConnectionsLoadError] = useState(false)
  const [testingConnectionId, setTestingConnectionId] = useState<string | null>(null)
  const [probeConnectionId, setProbeConnectionId] = useState<string | null>(null)
  const [probeOutputConnectionId, setProbeOutputConnectionId] = useState("")
  const [probeOutput, setProbeOutput] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<RemoteConnection | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
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
          remoteConnections.some((connection) => connection.id === current) ? current : "",
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

    return connections.filter((connection) => {
      const matchesStatus = statusFilter === "all" || connection.status === statusFilter
      if (!matchesStatus) return false
      if (!query) return true

      return [
        connection.name,
        connection.host,
        connection.username,
        connection.ssh_alias,
        connection.skill_instructions,
      ].some((value) => value.toLowerCase().includes(query))
    })
  }, [connections, search, statusFilter])

  const selectedConnection =
    filteredConnections.find((connection) => connection.id === selectedConnectionId) ?? null

  const resetFormState = () => {
    setForm(initialConnectionForm)
    setFormError(null)
    setFormErrorField(null)
    setEditingConnectionId(null)
    setDialogMode("create")
  }

  const handleDialogOpenChange = (open: boolean) => {
    setDialogOpen(open)
    if (!open) resetFormState()
  }

  const openCreateDialog = (authMethod: RemoteConnectionAuthMethod = "password") => {
    resetFormState()
    setForm({
      ...initialConnectionForm,
      auth_method: authMethod,
    })
    setDialogMode("create")
    setDialogOpen(true)
  }

  const openEditDialog = (connection: RemoteConnection) => {
    setSelectedConnectionId(connection.id)
    setForm(formFromConnection(connection))
    setFormError(null)
    setFormErrorField(null)
    setDialogMode("edit")
    setEditingConnectionId(connection.id)
    setDialogOpen(true)
  }

  const buildPayload = (): RemoteConnectionCreateInput | null => {
    const sshAlias = form.ssh_alias.trim()
    if (form.auth_method === "ssh_config" && !sshAlias) {
      setFormError(t("form.errors.sshAliasRequired"))
      setFormErrorField("ssh_alias")
      return null
    }

    const host = form.host.trim() || (form.auth_method === "ssh_config" ? sshAlias : "")
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

    const keyPath = form.key_path.trim()
    if (form.auth_method === "key_file" && !keyPath) {
      setFormError(t("form.errors.keyPathRequired"))
      setFormErrorField("key_path")
      return null
    }
    const password = form.password.trim()
    if (form.auth_method === "password" && !password) {
      setFormError(t("form.errors.passwordRequired"))
      setFormErrorField("password")
      return null
    }
    const privateKey = form.private_key.trim()
    if (form.auth_method === "private_key" && !privateKey) {
      setFormError(t("form.errors.privateKeyRequired"))
      setFormErrorField("private_key")
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
      password: form.auth_method === "password" ? password : null,
      private_key: form.auth_method === "private_key" ? privateKey : null,
      passphrase:
        form.auth_method === "private_key" ? form.passphrase.trim() || null : null,
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

  const handleDeleteConnection = async () => {
    if (!deleteTarget) return

    const deletingConnectionId = deleteTarget.id
    setIsDeleting(true)
    try {
      await deleteRemoteConnection(deletingConnectionId)
      removeConnectionLocally(deletingConnectionId)
      if (editingConnectionId === deletingConnectionId) {
        setDialogOpen(false)
        resetFormState()
      }
      toast.success(t("toasts.connectionDeleted", { name: deleteTarget.name }))
      setDeleteTarget(null)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        removeConnectionLocally(deletingConnectionId)
        if (editingConnectionId === deletingConnectionId) {
          setDialogOpen(false)
          resetFormState()
        }
        toast.error(t("delete.notFound", { name: deleteTarget.name }))
        setDeleteTarget(null)
      } else if (error instanceof ApiError && error.status === 409) {
        toast.error(t("delete.conflict", { name: deleteTarget.name }))
      } else {
        const message = error instanceof Error ? error.message : t("delete.failed", { name: deleteTarget.name })
        toast.error(message)
      }
    } finally {
      setIsDeleting(false)
    }
  }

  const removeConnectionLocally = (connectionId: string) => {
    setConnections((current) => {
      const nextConnections = current.filter((connection) => connection.id !== connectionId)
      if (selectedConnectionId === connectionId) {
        setSelectedConnectionId(nextConnections[0]?.id ?? "")
      }
      return nextConnections
    })
    if (probeOutputConnectionId === connectionId) {
      setProbeOutputConnectionId("")
      setProbeOutput("")
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

  const editingConnection = editingConnectionId
    ? connections.find((connection) => connection.id === editingConnectionId) ?? null
    : null
  const editingProbeOutput =
    editingConnection && probeOutputConnectionId === editingConnection.id ? probeOutput : ""

  return (
    <div className="relative h-full overflow-hidden bg-background">
      <div
        className={cn(
          "h-full overflow-y-auto transition-[padding] duration-200 ease-[cubic-bezier(.2,.8,.2,1)] motion-reduce:transition-none",
          dialogOpen && "lg:pr-[380px] xl:pr-[396px]",
        )}
      >
        <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col p-4 sm:p-6">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
              <p className="mt-0.5 text-sm text-muted-foreground">{t("subtitle")}</p>
            </div>
            {!dialogOpen ? (
              <Button onClick={() => openCreateDialog()}>
                <Plus className="mr-2 h-4 w-4" />
                {t("addNode")}
              </Button>
            ) : null}
          </div>

          <ConnectionDeleteDialog
            connection={deleteTarget}
            deleting={isDeleting}
            onCancel={() => setDeleteTarget(null)}
            onConfirm={handleDeleteConnection}
            t={t}
            tCommon={tCommon}
          />

          <div className="grid min-h-[calc(100dvh-9rem)] gap-5">
            <ConnectionList
              connections={connections}
              filteredConnections={filteredConnections}
              selectedConnection={selectedConnection}
              search={search}
              statusFilter={statusFilter}
              isLoading={isLoadingConnections}
              loadError={connectionsLoadError}
              onSearchChange={setSearch}
              onStatusFilterChange={setStatusFilter}
              onSelectConnection={setSelectedConnectionId}
              onEdit={openEditDialog}
            />
          </div>
        </div>
      </div>

      <ConnectionDialog
        open={dialogOpen}
        mode={dialogMode}
        connection={dialogMode === "edit" ? editingConnection : null}
        testing={editingConnection ? testingConnectionId === editingConnection.id : false}
        probing={editingConnection ? probeConnectionId === editingConnection.id : false}
        probeOutput={editingProbeOutput}
        form={form}
        formError={formError}
        formErrorField={formErrorField}
        isSaving={isSaving}
        onOpenChange={handleDialogOpenChange}
        onSubmit={handleSubmit}
        onFormChange={setForm}
        onAppendSkillText={appendSkillText}
        onTest={handleTestConnection}
        onRunProbe={handleRunProbe}
        onDelete={setDeleteTarget}
      />
    </div>
  )
}

function ConnectionDeleteDialog({
  connection,
  deleting,
  onCancel,
  onConfirm,
  t,
  tCommon,
}: {
  connection: RemoteConnection | null
  deleting: boolean
  onCancel: () => void
  onConfirm: () => void
  t: Translate
  tCommon: Translate
}) {
  return (
    <Dialog open={!!connection} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="rounded-[24px] sm:max-w-[430px]">
        <DialogHeader>
          <DialogTitle>{t("delete.title", { name: connection?.name ?? "" })}</DialogTitle>
          <DialogDescription className="leading-6">
            {t("delete.description")}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={onCancel} disabled={deleting}>
            {tCommon("cancel")}
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={deleting}>
            {deleting ? t("delete.deleting") : tCommon("delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
