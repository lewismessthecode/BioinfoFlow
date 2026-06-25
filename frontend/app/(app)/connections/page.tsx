"use client"

import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react"
import { BookOpenText, KeyRound, Plus, Search, Server } from "lucide-react"
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
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  demoConnectionNodes,
  fetchRemoteConnections,
  type RemoteConnection,
  type RemoteConnectionAuthMethod,
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
  status: RemoteConnectionStatus
  skill_instructions: string
}

const initialForm: ConnectionFormState = {
  name: "",
  host: "",
  port: "22",
  username: "",
  auth_method: "ssh_config",
  ssh_alias: "",
  key_path: "",
  status: "unknown",
  skill_instructions: "",
}

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

const authMethods: RemoteConnectionAuthMethod[] = ["ssh_config", "key_file", "agent"]
const statusOptions: RemoteConnectionStatus[] = ["online", "offline", "error", "unknown"]

function parsePort(value: string) {
  const port = Number.parseInt(value, 10)
  return Number.isFinite(port) && port > 0 ? port : 22
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
  const [connections, setConnections] = useState<RemoteConnection[]>(demoConnectionNodes)
  const [selectedConnectionId, setSelectedConnectionId] = useState(demoConnectionNodes[0]?.id ?? "")
  const [search, setSearch] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState<ConnectionFormState>(initialForm)

  useEffect(() => {
    let disposed = false

    fetchRemoteConnections()
      .then((remoteConnections) => {
        if (disposed || remoteConnections.length === 0) return
        setConnections(remoteConnections)
        setSelectedConnectionId((current) =>
          remoteConnections.some((connection) => connection.id === current)
            ? current
            : remoteConnections[0]?.id ?? "",
        )
      })
      .catch(() => {
        // Keep the demo fallback available when the backend is not running.
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

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const host = form.host.trim()
    const name = form.name.trim() || host
    if (!host || !name) return

    const nextConnection: RemoteConnection = {
      id: `connection-${Date.now()}`,
      name,
      host,
      port: parsePort(form.port),
      username: form.username.trim() || t("form.defaultUsername"),
      auth_method: form.auth_method,
      ssh_alias: form.ssh_alias.trim(),
      key_path: form.key_path.trim(),
      status: form.status,
      skill_instructions: form.skill_instructions.trim(),
    }

    setConnections((current) => [nextConnection, ...current])
    setSelectedConnectionId(nextConnection.id)
    setDialogOpen(false)
    setForm(initialForm)
    toast.success(t("toasts.connectionAdded", { name }))
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="w-fit rounded-full px-4">
                <Plus className="h-4 w-4" />
                {t("addNode")}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[min(88vh,760px)] overflow-y-auto rounded-3xl border-border/70 bg-card p-0 text-card-foreground shadow-2xl shadow-foreground/20 sm:max-w-2xl">
              <form onSubmit={handleSubmit}>
                <DialogHeader className="border-b border-border/70 px-6 py-5">
                  <DialogTitle>{t("dialog.title")}</DialogTitle>
                  <DialogDescription>{t("dialog.description")}</DialogDescription>
                </DialogHeader>

                <div className="grid gap-6 px-6 py-5">
                  <section className="grid gap-4">
                    <FormSectionTitle title={t("sections.connection")} icon={<Server className="h-4 w-4" />} />
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="grid gap-2">
                        <Label htmlFor="connection-name">{t("fields.name")}</Label>
                        <Input
                          id="connection-name"
                          value={form.name}
                          onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                          placeholder={t("form.placeholders.name")}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="connection-host">{t("fields.host")}</Label>
                        <Input
                          id="connection-host"
                          value={form.host}
                          onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))}
                          placeholder={t("form.placeholders.host")}
                          required
                        />
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <Label>{t("fields.status")}</Label>
                      <Select
                        value={form.status}
                        onValueChange={(value) =>
                          setForm((current) => ({ ...current, status: value as RemoteConnectionStatus }))
                        }
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {statusOptions.map((status) => (
                            <SelectItem key={status} value={status}>
                              <span className="flex items-center gap-2">
                                <StatusDot status={status} className="h-2 w-2 shadow-[0_0_0_3px]" />
                                {t(`status.${status}`)}
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </section>

                  <section className="grid gap-4">
                    <FormSectionTitle title={t("sections.ssh")} icon={<KeyRound className="h-4 w-4" />} />
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="grid gap-2">
                        <Label htmlFor="connection-port">{t("fields.port")}</Label>
                        <Input
                          id="connection-port"
                          value={form.port}
                          inputMode="numeric"
                          onChange={(event) => setForm((current) => ({ ...current, port: event.target.value }))}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="connection-username">{t("fields.username")}</Label>
                        <Input
                          id="connection-username"
                          value={form.username}
                          onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                          placeholder={t("form.placeholders.username")}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label>{t("fields.auth")}</Label>
                        <Select
                          value={form.auth_method}
                          onValueChange={(value) =>
                            setForm((current) => ({
                              ...current,
                              auth_method: value as RemoteConnectionAuthMethod,
                            }))
                          }
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {authMethods.map((method) => (
                              <SelectItem key={method} value={method}>
                                {t(`auth.${method}`)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="grid gap-2">
                        <Label htmlFor="connection-ssh-alias">{t("fields.sshAlias")}</Label>
                        <Input
                          id="connection-ssh-alias"
                          value={form.ssh_alias}
                          onChange={(event) => setForm((current) => ({ ...current, ssh_alias: event.target.value }))}
                          placeholder={t("form.placeholders.sshAlias")}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="connection-key-path">{t("fields.keyPath")}</Label>
                        <Input
                          id="connection-key-path"
                          value={form.key_path}
                          onChange={(event) => setForm((current) => ({ ...current, key_path: event.target.value }))}
                          placeholder={t("form.placeholders.keyPath")}
                        />
                      </div>
                    </div>
                    <p className="text-xs leading-5 text-muted-foreground">{t("form.secretsNote")}</p>
                  </section>

                  <section className="grid gap-3">
                    <FormSectionTitle title={t("sections.agentSkill")} icon={<BookOpenText className="h-4 w-4" />} />
                    <p className="text-sm leading-6 text-muted-foreground">{t("form.skillGuidance")}</p>
                    <TextFieldArea
                      id="connection-skill-instructions"
                      label={t("fields.skillInstructions")}
                      value={form.skill_instructions}
                      onChange={(value) => setForm((current) => ({ ...current, skill_instructions: value }))}
                      placeholder={t("form.placeholders.skillInstructions")}
                    />
                  </section>
                </div>

                <DialogFooter className="border-t border-border/70 px-6 py-4">
                  <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                    {tCommon("cancel")}
                  </Button>
                  <Button type="submit">{t("dialog.add")}</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

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
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("searchPlaceholder")}
                  className="h-9 pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="grid gap-2 p-2">
              {filteredConnections.length > 0 ? (
                filteredConnections.map((connection) => {
                  const selected = selectedConnection ? connection.id === selectedConnection.id : false

                  return (
                    <button
                      key={connection.id}
                      type="button"
                      onClick={() => setSelectedConnectionId(connection.id)}
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
                      <span className="text-xs font-medium text-muted-foreground">{t("detail.currentContext")}</span>
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
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-h-36 resize-none"
      />
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3 rounded-2xl bg-muted/20 p-4">
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
    <div className="rounded-2xl bg-background/70 p-4">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">{title}</p>
      <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-foreground">
        {value || empty}
      </pre>
    </div>
  )
}
