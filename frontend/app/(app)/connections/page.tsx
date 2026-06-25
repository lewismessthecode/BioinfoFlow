"use client"

import {
  type DragEvent,
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  BookOpenText,
  CheckCircle2,
  FileText,
  KeyRound,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  TerminalSquare,
  Upload,
} from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  createRemoteConnection,
  demoConnectionNodes,
  fetchRemoteConnections,
  runRemoteConnectionCommand,
  testRemoteConnection,
  updateRemoteConnection,
  type RemoteConnection,
  type RemoteConnectionAuthMethod,
  type RemoteConnectionCreateInput,
  type RemoteConnectionStatus,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

type ConnectionFormState = {
  name: string
  host: string
  port: string
  username: string
  auth_method: RemoteConnectionAuthMethod
  ssh_alias: string
  key_path: string
  skill_instructions: string
}

type DialogMode = "create" | "edit"
type FormErrorField = "port" | "ssh_alias" | "key_path" | null

const initialForm: ConnectionFormState = {
  name: "",
  host: "",
  port: "22",
  username: "",
  auth_method: "ssh_config",
  ssh_alias: "",
  key_path: "",
  skill_instructions: "",
}

const authMethods: RemoteConnectionAuthMethod[] = ["ssh_config", "key_file", "agent"]
const skillPresetKeys = ["nextflowHpc", "slurmDiagnostics", "readonlyInspection"] as const

const statusDotClassNames: Record<RemoteConnectionStatus, string> = {
  online: "bg-emerald-500 shadow-emerald-500/40",
  offline: "bg-rose-500 shadow-rose-500/40",
  error: "bg-amber-500 shadow-amber-500/40",
  unknown: "bg-slate-400 shadow-slate-400/30",
}

const statusBorderClassNames: Record<RemoteConnectionStatus, string> = {
  online: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  offline: "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  error: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  unknown: "border-slate-500/25 bg-slate-500/10 text-slate-700 dark:text-slate-300",
}

function parsePort(value: string): number | null {
  const port = Number.parseInt(value, 10)
  return Number.isFinite(port) && port >= 1 && port <= 65535 ? port : null
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

function StatusDot({ status, className }: { status: RemoteConnectionStatus; className?: string }) {
  return (
    <span
      className={cn("h-2.5 w-2.5 rounded-full shadow-[0_0_0_4px]", statusDotClassNames[status], className)}
      aria-hidden="true"
    />
  )
}

export default function ConnectionsPage() {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")
  const [connections, setConnections] = useState<RemoteConnection[]>([])
  const [selectedConnectionId, setSelectedConnectionId] = useState("")
  const [search, setSearch] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>("create")
  const [editingConnectionId, setEditingConnectionId] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionFormState>(initialForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [formErrorField, setFormErrorField] = useState<FormErrorField>(null)
  const [skillDragActive, setSkillDragActive] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isLoadingConnections, setIsLoadingConnections] = useState(true)
  const [testingConnectionId, setTestingConnectionId] = useState<string | null>(null)
  const [probeConnectionId, setProbeConnectionId] = useState<string | null>(null)
  const [probeOutput, setProbeOutput] = useState("")

  useEffect(() => {
    let disposed = false

    fetchRemoteConnections()
      .then((remoteConnections) => {
        if (disposed) return
        setConnections(remoteConnections)
        setSelectedConnectionId((current) =>
          remoteConnections.some((connection) => connection.id === current)
            ? current
            : remoteConnections[0]?.id ?? "",
        )
      })
      .catch(() => {
        if (disposed) return
        setConnections(demoConnectionNodes)
        setSelectedConnectionId(demoConnectionNodes[0]?.id ?? "")
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
    connections.find((connection) => connection.id === selectedConnectionId) ?? connections[0]

  const resetFormState = () => {
    setForm(initialForm)
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
    const name = form.name.trim() || host
    if (!host || !name) return null

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
      ssh_alias: sshAlias || null,
      key_path: form.auth_method === "key_file" ? keyPath : null,
      skill_instructions: form.skill_instructions.trim() || null,
    }
  }

  const upsertConnection = (nextConnection: RemoteConnection) => {
    setConnections((current) => {
      if (current.some((connection) => connection.id === nextConnection.id)) {
        return current.map((connection) =>
          connection.id === nextConnection.id ? nextConnection : connection,
        )
      }
      return [nextConnection, ...current]
    })
    setSelectedConnectionId(nextConnection.id)
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
    setTestingConnectionId(connection.id)
    try {
      const result = await testRemoteConnection(connection.id)
      upsertConnection(result.connection)
      if (result.status === "online") {
        toast.success(t("toasts.testSucceeded", { name: result.connection.name }))
      } else {
        toast.error(result.error || t("toasts.testFailed", { name: result.connection.name }))
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t("toasts.testFailed", { name: connection.name })
      toast.error(message)
    } finally {
      setTestingConnectionId(null)
    }
  }

  const handleRunProbe = async (connection: RemoteConnection) => {
    setProbeConnectionId(connection.id)
    setProbeOutput("")
    try {
      const result = await runRemoteConnectionCommand(connection.id, {
        command: "printf bioinfoflow-ok",
        timeout_seconds: 10,
        onFrame: (frame) => {
          if ((frame.type === "stdout" || frame.type === "stderr" || frame.type === "truncated") && frame.data) {
            setProbeOutput((current) => `${current}${frame.data}`)
          }
          if (frame.type === "error" && frame.message) {
            setProbeOutput((current) => `${current}${frame.message}\n`)
          }
        },
      })
      setProbeOutput((current) => current || result.output || t("probe.emptyOutput"))
    } catch (error) {
      const message = error instanceof Error ? error.message : t("probe.failed")
      setProbeOutput(message)
      toast.error(message)
    } finally {
      setProbeConnectionId(null)
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

  const handleSkillDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setSkillDragActive(false)
    const file = event.dataTransfer.files?.[0]
    if (!file) return
    try {
      appendSkillText(await file.text())
      toast.success(t("toasts.skillImported"))
    } catch {
      toast.error(t("form.errors.skillFileFailed"))
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Button className="w-fit rounded-full px-4" onClick={openCreateDialog}>
            <Plus className="h-4 w-4" />
            {t("addNode")}
          </Button>
        </div>

        <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}>
          <DialogContent className="max-h-[min(92vh,780px)] overflow-hidden rounded-2xl border-border/70 bg-card p-0 text-card-foreground shadow-2xl shadow-foreground/20 sm:max-w-4xl">
            <form onSubmit={handleSubmit} noValidate className="flex max-h-[min(92vh,780px)] flex-col">
              <DialogHeader className="border-b border-border/70 px-5 py-3.5">
                <DialogTitle>
                  {dialogMode === "edit" ? t("dialog.editTitle") : t("dialog.title")}
                </DialogTitle>
                <DialogDescription>{t("dialog.description")}</DialogDescription>
              </DialogHeader>

              <div className="grid gap-4 overflow-y-auto px-5 py-3.5 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.9fr)] lg:overflow-visible">
                <div className="grid gap-3">
                  <section className="grid gap-2.5">
                    <FormSectionTitle title={t("sections.connection")} icon={<Server className="h-4 w-4" />} />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label={t("fields.name")} htmlFor="connection-name">
                        <Input
                          id="connection-name"
                          value={form.name}
                          onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                          placeholder={t("form.placeholders.name")}
                        />
                      </Field>
                      <Field label={t("fields.host")} htmlFor="connection-host">
                        <Input
                          id="connection-host"
                          value={form.host}
                          onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))}
                          placeholder={t("form.placeholders.host")}
                          required
                        />
                      </Field>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-[minmax(84px,0.55fr)_minmax(0,1fr)_minmax(0,1fr)]">
                      <Field label={t("fields.port")} htmlFor="connection-port">
                        <Input
                          id="connection-port"
                          value={form.port}
                          inputMode="numeric"
                          onChange={(event) => setForm((current) => ({ ...current, port: event.target.value }))}
                          aria-invalid={formErrorField === "port"}
                          aria-describedby={formErrorField === "port" ? "connection-form-error" : undefined}
                        />
                      </Field>
                      <Field label={t("fields.username")} htmlFor="connection-username">
                        <Input
                          id="connection-username"
                          value={form.username}
                          onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                          placeholder={t("form.placeholders.username")}
                        />
                      </Field>
                      <Field label={t("fields.sshAlias")} htmlFor="connection-ssh-alias">
                        <Input
                          id="connection-ssh-alias"
                          value={form.ssh_alias}
                          onChange={(event) => setForm((current) => ({ ...current, ssh_alias: event.target.value }))}
                          placeholder={t("form.placeholders.sshAlias")}
                          required={form.auth_method === "ssh_config"}
                          aria-invalid={formErrorField === "ssh_alias"}
                          aria-describedby={formErrorField === "ssh_alias" ? "connection-form-error" : undefined}
                        />
                      </Field>
                    </div>
                  </section>

                  <section className="grid gap-2.5">
                    <FormSectionTitle title={t("sections.ssh")} icon={<KeyRound className="h-4 w-4" />} />
                    <div aria-label={t("fields.auth")} className="grid gap-2 sm:grid-cols-3">
                      {authMethods.map((method) => (
                        <AuthMethodButton
                          key={method}
                          method={method}
                          selected={form.auth_method === method}
                          title={t(`auth.${method}`)}
                          description={t(`authHelp.${method}`)}
                          onSelect={() =>
                            setForm((current) => ({
                              ...current,
                              auth_method: method,
                              key_path: method === "key_file" ? current.key_path : "",
                            }))
                          }
                        />
                      ))}
                    </div>
                    <Field label={t("fields.keyPath")} htmlFor="connection-key-path">
                      <Input
                        id="connection-key-path"
                        value={form.key_path}
                        onChange={(event) => setForm((current) => ({ ...current, key_path: event.target.value }))}
                        placeholder={t("form.placeholders.keyPath")}
                        required={form.auth_method === "key_file"}
                        disabled={form.auth_method !== "key_file"}
                        aria-invalid={formErrorField === "key_path"}
                        aria-describedby={formErrorField === "key_path" ? "connection-form-error" : undefined}
                      />
                    </Field>
                    <p className="text-xs leading-5 text-muted-foreground">{t("form.secretsNote")}</p>
                  </section>
                </div>

                <section className="grid content-start gap-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <FormSectionTitle title={t("sections.agentSkill")} icon={<BookOpenText className="h-4 w-4" />} />
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button type="button" variant="outline" size="sm" className="h-8">
                          <FileText className="h-4 w-4" />
                          {t("actions.insertPreset")}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-56">
                        {skillPresetKeys.map((key) => (
                          <DropdownMenuItem
                            key={key}
                            onSelect={() => appendSkillText(t(`skillPresets.${key}.text`))}
                          >
                            {t(`skillPresets.${key}.name`)}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <TextFieldArea
                    id="connection-skill-instructions"
                    label={t("fields.skillInstructions")}
                    value={form.skill_instructions}
                    onChange={(value) => setForm((current) => ({ ...current, skill_instructions: value }))}
                    placeholder={t("form.placeholders.skillInstructions")}
                  />
                  <div
                    role="button"
                    tabIndex={0}
                    onDragEnter={(event) => {
                      event.preventDefault()
                      setSkillDragActive(true)
                    }}
                    onDragOver={(event) => event.preventDefault()}
                    onDragLeave={() => setSkillDragActive(false)}
                    onDrop={handleSkillDrop}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border border-dashed px-3 py-2 text-sm text-muted-foreground transition",
                      skillDragActive ? "border-primary/60 bg-primary/10 text-foreground" : "border-border bg-muted/20",
                    )}
                  >
                    <Upload className="h-4 w-4" />
                    <div>
                      <p className="font-medium text-foreground">{t("skillDrop.title")}</p>
                      <p className="text-xs">{t("skillDrop.hint")}</p>
                    </div>
                  </div>
                </section>
              </div>

              {formError ? (
                <div
                  id="connection-form-error"
                  role="alert"
                  aria-live="polite"
                  className="mx-5 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {formError}
                </div>
              ) : null}
              <DialogFooter className="border-t border-border/70 px-5 py-3">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)} disabled={isSaving}>
                  {tCommon("cancel")}
                </Button>
                <Button type="submit" disabled={isSaving}>
                  {isSaving
                    ? t("dialog.saving")
                    : dialogMode === "edit"
                      ? t("dialog.save")
                      : t("dialog.add")}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <div className="grid gap-4 lg:grid-cols-[minmax(280px,34%)_minmax(0,1fr)]">
          <Card className="overflow-hidden border-border/70 bg-card py-0 shadow-sm shadow-foreground/5">
            <CardHeader className="border-b border-border/70 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{t("list.title")}</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">{t("list.description")}</p>
                </div>
                <Server className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="relative mt-3">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  aria-label={t("searchPlaceholder")}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("searchPlaceholder")}
                  className="h-9 pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="grid gap-2 p-2">
              {isLoadingConnections ? (
                <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                  {t("list.loading")}
                </div>
              ) : filteredConnections.length > 0 ? (
                filteredConnections.map((connection) => {
                  const selected = selectedConnection ? connection.id === selectedConnection.id : false

                  return (
                    <button
                      key={connection.id}
                      type="button"
                      onClick={() => setSelectedConnectionId(connection.id)}
                      aria-pressed={selected}
                      className={cn(
                        "group rounded-xl border p-3 text-left transition hover:border-primary/25 hover:bg-muted/35",
                        selected
                          ? "border-primary/35 bg-primary/10 shadow-sm shadow-primary/5"
                          : "border-transparent bg-transparent",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-background/70 text-muted-foreground group-hover:text-foreground">
                          <Server className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-foreground">{connection.name}</p>
                              <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                                {connection.username}@{connection.host}:{connection.port}
                              </p>
                            </div>
                            <span className="inline-flex items-center gap-2 pt-0.5 text-xs text-muted-foreground">
                              <StatusDot status={connection.status} />
                              {t(`status.${connection.status}`)}
                            </span>
                          </div>
                          {connection.ssh_alias ? (
                            <p className="mt-2 truncate text-xs text-muted-foreground">
                              {t("detail.aliasPrefix")}{" "}
                              <span className="font-mono text-foreground">{connection.ssh_alias}</span>
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </button>
                  )
                })
              ) : (
                <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                  {t("list.empty")}
                </div>
              )}
            </CardContent>
          </Card>

          {selectedConnection ? (
            <section>
              <Card className="overflow-hidden border-border/70 bg-card py-0 shadow-sm shadow-foreground/5">
                <CardContent className="p-0">
                  <div className="border-b border-border/70 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-background/80 text-foreground">
                          <Server className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="truncate text-base font-semibold tracking-tight text-foreground">
                              {selectedConnection.name}
                            </h2>
                            <Badge
                              variant="outline"
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-xs",
                                statusBorderClassNames[selectedConnection.status],
                              )}
                            >
                              <StatusDot status={selectedConnection.status} className="h-2 w-2 shadow-none" />
                              {t(`status.${selectedConnection.status}`)}
                            </Badge>
                          </div>
                          <p className="mt-0.5 font-mono text-sm text-muted-foreground">
                            {selectedConnection.username}@{selectedConnection.host}:{selectedConnection.port}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleTestConnection(selectedConnection)}
                          disabled={testingConnectionId === selectedConnection.id}
                        >
                          <RefreshCw
                            className={cn(
                              "h-4 w-4",
                              testingConnectionId === selectedConnection.id && "animate-spin",
                            )}
                          />
                          {testingConnectionId === selectedConnection.id
                            ? t("actions.testing")
                            : t("actions.testConnection")}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => openEditDialog(selectedConnection)}
                        >
                          <Pencil className="h-4 w-4" />
                          {t("actions.editConnection")}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => handleRunProbe(selectedConnection)}
                          disabled={probeConnectionId === selectedConnection.id}
                        >
                          <Play className="h-4 w-4" />
                          {probeConnectionId === selectedConnection.id ? t("actions.runningProbe") : t("actions.runProbe")}
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 p-4">
                    <div className="grid gap-3 xl:grid-cols-2">
                      <DetailSection title={t("sections.connection")}>
                        <DetailGrid>
                          <DetailItem label={t("fields.name")} value={selectedConnection.name} />
                          <DetailItem label={t("fields.host")} value={selectedConnection.host} mono />
                          <DetailItem label={t("fields.status")} value={t(`status.${selectedConnection.status}`)} />
                        </DetailGrid>
                        {selectedConnection.status_message ? (
                          <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
                            {selectedConnection.status_message}
                          </div>
                        ) : null}
                      </DetailSection>

                      <DetailSection title={t("sections.ssh")}>
                        <DetailGrid>
                          <DetailItem label={t("fields.port")} value={String(selectedConnection.port)} mono />
                          <DetailItem label={t("fields.username")} value={selectedConnection.username} mono />
                          <DetailItem label={t("fields.auth")} value={t(`auth.${selectedConnection.auth_method}`)} />
                          <DetailItem
                            label={t("fields.sshAlias")}
                            value={selectedConnection.ssh_alias || t("empty.notSet")}
                            mono
                          />
                          <DetailItem
                            label={t("fields.keyPath")}
                            value={selectedConnection.key_path || t("empty.notSet")}
                            mono
                          />
                        </DetailGrid>
                        <p className="text-xs leading-5 text-muted-foreground">{t("detail.secretsNote")}</p>
                      </DetailSection>
                    </div>

                    <DetailSection title={t("sections.agentSkill")}>
                      <p className="text-sm leading-6 text-muted-foreground">{t("detail.skillGuidance")}</p>
                      <TextPanel
                        title={t("fields.skillInstructions")}
                        value={selectedConnection.skill_instructions}
                        empty={t("empty.skillInstructions")}
                      />
                    </DetailSection>

                    <DetailSection title={t("probe.title")}>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <TerminalSquare className="h-4 w-4" />
                        <span>{t("probe.description")}</span>
                      </div>
                      <pre className="min-h-12 rounded-xl bg-background/80 p-3 font-mono text-xs leading-5 text-foreground">
                        {probeOutput || t("probe.placeholder")}
                      </pre>
                    </DetailSection>
                  </div>
                </CardContent>
              </Card>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: ReactNode
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

function FormSectionTitle({ title, icon }: { title: string; icon: ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
      <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border/70 bg-muted/50 text-muted-foreground">
        {icon}
      </span>
      {title}
    </div>
  )
}

function AuthMethodButton({
  method,
  selected,
  title,
  description,
  onSelect,
}: {
  method: RemoteConnectionAuthMethod
  selected: boolean
  title: string
  description: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "min-h-[4.75rem] rounded-xl border p-2.5 text-left transition hover:border-primary/40 hover:bg-muted/35",
        selected ? "border-primary/45 bg-primary/10 shadow-sm shadow-primary/10" : "border-border/70 bg-background/70",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        {selected ? <CheckCircle2 className="h-4 w-4 text-primary" /> : null}
      </span>
      <span className="mt-1 block text-xs leading-4 text-muted-foreground">{description}</span>
      <span className="sr-only">{method}</span>
    </button>
  )
}

function TextFieldArea({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  placeholder: string
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-h-28 resize-none lg:min-h-40"
      />
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3 rounded-xl bg-muted/20 p-4">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  )
}

function DetailGrid({ children }: { children: ReactNode }) {
  return <dl className="grid gap-3 sm:grid-cols-2">{children}</dl>
}

function DetailItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 break-words text-sm font-medium text-foreground", mono && "font-mono")}>{value}</dd>
    </div>
  )
}

function TextPanel({ title, value, empty }: { title: string; value: string; empty: string }) {
  return (
    <div className="rounded-xl bg-background/70 p-4">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">{title}</p>
      <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-foreground">
        {value || empty}
      </pre>
    </div>
  )
}
