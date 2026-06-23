"use client"

import { type FormEvent, type ReactNode, useMemo, useState } from "react"
import { FolderOpen, Plus, Search, Server, TerminalSquare, X } from "lucide-react"
import { useLocale, useTranslations } from "next-intl"
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
  createLocalizedDemoText,
  defaultDemoConnectionTags,
  demoConnectionNodes,
  demoConnectionTagStyles,
  getDemoConnectionText,
  type DemoConnectionNode,
  type DemoConnectionStatus,
} from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

type HostFormState = {
  address: string
  label: string
  group: string
  status: DemoConnectionStatus
  tags: string[]
  port: string
  username: string
  auth: DemoConnectionNode["ssh"]["auth"]
  skills: string
  prompt: string
  paths: string
  apis: string
  environmentVariables: string
  startupSnippet: string
}

const initialForm: HostFormState = {
  address: "",
  label: "",
  group: "",
  status: "unknown",
  tags: [],
  port: "22",
  username: "",
  auth: "key",
  skills: "",
  prompt: "",
  paths: "",
  apis: "",
  environmentVariables: "",
  startupSnippet: "",
}

const statusDotClassNames: Record<DemoConnectionStatus, string> = {
  online: "bg-emerald-500 shadow-emerald-500/40",
  offline: "bg-rose-500 shadow-rose-500/40",
  partial: "bg-amber-500 shadow-amber-500/40",
  unknown: "bg-slate-400 shadow-slate-400/30",
}

const statusBorderClassNames: Record<DemoConnectionStatus, string> = {
  online: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  offline: "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  partial: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  unknown: "border-slate-500/25 bg-slate-500/10 text-slate-700 dark:text-slate-300",
}

const authMethods: Array<DemoConnectionNode["ssh"]["auth"]> = [
  "password",
  "key",
  "certificate",
  "fido2",
]

const statusOptions: DemoConnectionStatus[] = ["online", "offline", "partial", "unknown"]

function parseList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseSkills(value: string) {
  return value
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function StatusDot({ status, className }: { status: DemoConnectionStatus; className?: string }) {
  return (
    <span
      className={cn("h-2.5 w-2.5 rounded-full shadow-[0_0_0_4px]", statusDotClassNames[status], className)}
      aria-hidden="true"
    />
  )
}

function ConnectionTag({ tag, active = true }: { tag: string; active?: boolean }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "rounded-full border px-2.5 py-1 text-[11px] font-medium",
        demoConnectionTagStyles[tag] ?? "border-border bg-muted/60 text-muted-foreground",
        !active && "opacity-45",
      )}
    >
      {tag}
    </Badge>
  )
}

export default function ConnectionsPage() {
  const locale = useLocale()
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")
  const [nodes, setNodes] = useState<DemoConnectionNode[]>(demoConnectionNodes)
  const [selectedNodeId, setSelectedNodeId] = useState(demoConnectionNodes[0]?.id ?? "")
  const [search, setSearch] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState<HostFormState>(initialForm)
  const [tagInput, setTagInput] = useState("")

  const allTags = useMemo(() => {
    const seen = new Set([...defaultDemoConnectionTags, ...nodes.flatMap((node) => node.tags)])
    return Array.from(seen)
  }, [nodes])

  const filteredNodes = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return nodes

    return nodes.filter((node) => {
      const label = getDemoConnectionText(node.label, locale).toLowerCase()
      const group = getDemoConnectionText(node.group, locale).toLowerCase()
      return [node.address, label, group, ...node.tags, ...node.skills].some((value) =>
        value.toLowerCase().includes(query),
      )
    })
  }, [locale, nodes, search])

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0]

  const toggleTag = (tag: string) => {
    setForm((current) => ({
      ...current,
      tags: current.tags.includes(tag)
        ? current.tags.filter((item) => item !== tag)
        : [...current.tags, tag],
    }))
  }

  const addCustomTag = () => {
    const tag = tagInput.trim()
    if (!tag) return
    setForm((current) => ({
      ...current,
      tags: current.tags.includes(tag) ? current.tags : [...current.tags, tag],
    }))
    setTagInput("")
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const address = form.address.trim()
    if (!address) return

    const apis = parseList(form.apis).map((baseUrl, index) => ({
      name: t("form.defaultApiName", { index: index + 1 }),
      baseUrl,
    }))
    const nextNode: DemoConnectionNode = {
      id: `node-demo-${Date.now()}`,
      address,
      label: createLocalizedDemoText(form.label.trim() || address),
      group: createLocalizedDemoText(form.group.trim() || t("form.defaultGroup")),
      status: form.status,
      tags: form.tags,
      ssh: {
        port: Number.parseInt(form.port, 10) || 22,
        username: form.username.trim() || t("form.defaultUsername"),
        auth: form.auth,
      },
      skills: parseSkills(form.skills),
      prompts: form.prompt.trim() ? [createLocalizedDemoText(form.prompt.trim())] : [],
      paths: parseList(form.paths),
      apis,
      environmentVariables: parseList(form.environmentVariables),
      startupSnippet: form.startupSnippet.trim(),
    }

    setNodes((current) => [nextNode, ...current])
    setSelectedNodeId(nextNode.id)
    setDialogOpen(false)
    setForm(initialForm)
    setTagInput("")
    toast.success(t("toasts.nodeAdded", { address }))
  }

  return (
    <div className="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.09),transparent_34rem)]">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 sm:p-6">
        <header className="overflow-hidden rounded-[2rem] border border-border/70 bg-card/85 shadow-xl shadow-foreground/5 backdrop-blur">
          <div className="relative grid gap-6 p-5 sm:p-7 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="absolute inset-y-0 right-0 hidden w-72 bg-[linear-gradient(135deg,transparent,hsl(var(--primary)/0.12))] lg:block" />
            <div className="relative space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="rounded-full px-3 py-1 text-xs">
                  {t("demoBadge")}
                </Badge>
                <span className="rounded-full border border-border/70 px-3 py-1 text-xs text-muted-foreground">
                  {t("nodeCount", { count: nodes.length })}
                </span>
              </div>
              <div className="space-y-2">
                <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                  {t("title")}
                </h1>
                <p className="max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                  {t("subtitle")}
                </p>
              </div>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="relative rounded-full px-4">
                  <Plus className="h-4 w-4" />
                  {t("addNode")}
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[min(88vh,760px)] overflow-y-auto rounded-3xl border-border/70 bg-card p-0 text-card-foreground shadow-2xl shadow-foreground/20 sm:max-w-3xl">
                <form onSubmit={handleSubmit}>
                  <DialogHeader className="border-b border-border/70 px-6 py-5">
                    <DialogTitle>{t("dialog.title")}</DialogTitle>
                    <DialogDescription>{t("dialog.description")}</DialogDescription>
                  </DialogHeader>

                  <div className="grid gap-6 px-6 py-5">
                    <section className="grid gap-4">
                      <FormSectionTitle title={t("sections.address")} icon={<Server className="h-4 w-4" />} />
                      <div className="grid gap-2">
                        <Label htmlFor="connection-address">{t("fields.address")}</Label>
                        <Input
                          id="connection-address"
                          value={form.address}
                          onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))}
                          placeholder={t("form.placeholders.address")}
                          required
                        />
                      </div>
                    </section>

                    <section className="grid gap-4">
                      <FormSectionTitle title={t("sections.general")} icon={<TerminalSquare className="h-4 w-4" />} />
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="grid gap-2">
                          <Label htmlFor="connection-label">{t("fields.label")}</Label>
                          <Input
                            id="connection-label"
                            value={form.label}
                            onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
                            placeholder={t("form.placeholders.label")}
                          />
                        </div>
                        <div className="grid gap-2">
                          <Label htmlFor="connection-group">{t("fields.group")}</Label>
                          <Input
                            id="connection-group"
                            value={form.group}
                            onChange={(event) => setForm((current) => ({ ...current, group: event.target.value }))}
                            placeholder={t("form.placeholders.group")}
                          />
                        </div>
                      </div>
                      <div className="grid gap-2">
                        <Label>{t("fields.status")}</Label>
                        <Select
                          value={form.status}
                          onValueChange={(value) =>
                            setForm((current) => ({ ...current, status: value as DemoConnectionStatus }))
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
                      <div className="grid gap-3">
                        <Label>{t("fields.tags")}</Label>
                        <div className="flex flex-wrap gap-2">
                          {allTags.map((tag) => {
                            const selected = form.tags.includes(tag)
                            return (
                              <button
                                key={tag}
                                type="button"
                                aria-pressed={selected}
                                onClick={() => toggleTag(tag)}
                                className={cn(
                                  "rounded-full outline-none ring-offset-background transition focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                                  !selected && "opacity-60 hover:opacity-100",
                                )}
                              >
                                <ConnectionTag tag={tag} active={selected} />
                              </button>
                            )
                          })}
                        </div>
                        <div className="flex gap-2">
                          <Input
                            value={tagInput}
                            onChange={(event) => setTagInput(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault()
                                addCustomTag()
                              }
                            }}
                            placeholder={t("form.placeholders.tag")}
                          />
                          <Button type="button" variant="outline" onClick={addCustomTag}>
                            {t("form.addTag")}
                          </Button>
                        </div>
                        {form.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {form.tags.map((tag) => (
                              <button
                                key={tag}
                                type="button"
                                className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                                onClick={() => toggleTag(tag)}
                              >
                                {tag}
                                <X className="h-3 w-3" />
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </section>

                    <section className="grid gap-4">
                      <FormSectionTitle title={t("sections.ssh")} icon={<TerminalSquare className="h-4 w-4" />} />
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
                            value={form.auth}
                            onValueChange={(value) =>
                              setForm((current) => ({
                                ...current,
                                auth: value as DemoConnectionNode["ssh"]["auth"],
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
                    </section>

                    <section className="grid gap-4">
                      <FormSectionTitle title={t("sections.agentContext")} icon={<FolderOpen className="h-4 w-4" />} />
                      <div className="grid gap-4 sm:grid-cols-2">
                        <TextFieldArea
                          id="connection-skills"
                          label={t("fields.skills")}
                          value={form.skills}
                          onChange={(value) => setForm((current) => ({ ...current, skills: value }))}
                          placeholder={t("form.placeholders.skills")}
                        />
                        <TextFieldArea
                          id="connection-paths"
                          label={t("fields.paths")}
                          value={form.paths}
                          onChange={(value) => setForm((current) => ({ ...current, paths: value }))}
                          placeholder={t("form.placeholders.paths")}
                        />
                        <TextFieldArea
                          id="connection-apis"
                          label={t("fields.apis")}
                          value={form.apis}
                          onChange={(value) => setForm((current) => ({ ...current, apis: value }))}
                          placeholder={t("form.placeholders.apis")}
                        />
                        <TextFieldArea
                          id="connection-env"
                          label={t("fields.environmentVariables")}
                          value={form.environmentVariables}
                          onChange={(value) =>
                            setForm((current) => ({ ...current, environmentVariables: value }))
                          }
                          placeholder={t("form.placeholders.environmentVariables")}
                        />
                      </div>
                      <TextFieldArea
                        id="connection-prompt"
                        label={t("fields.prompt")}
                        value={form.prompt}
                        onChange={(value) => setForm((current) => ({ ...current, prompt: value }))}
                        placeholder={t("form.placeholders.prompt")}
                      />
                      <TextFieldArea
                        id="connection-startup"
                        label={t("fields.startupSnippet")}
                        value={form.startupSnippet}
                        onChange={(value) => setForm((current) => ({ ...current, startupSnippet: value }))}
                        placeholder={t("form.placeholders.startupSnippet")}
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
        </header>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(380px,1.1fr)]">
          <Card className="overflow-hidden border-border/70 bg-card/85 py-0 shadow-xl shadow-foreground/5 backdrop-blur">
            <CardHeader className="border-b border-border/70 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{t("list.title")}</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">{t("list.description")}</p>
                </div>
                <Server className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="relative mt-4">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t("searchPlaceholder")}
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="grid gap-2 p-3">
              {filteredNodes.length > 0 ? (
                filteredNodes.map((node) => {
                  const selected = node.id === selectedNode.id
                  const label = getDemoConnectionText(node.label, locale)
                  const group = getDemoConnectionText(node.group, locale)
                  return (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() => setSelectedNodeId(node.id)}
                      className={cn(
                        "group rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:border-primary/30 hover:bg-muted/40 hover:shadow-lg hover:shadow-foreground/5",
                        selected
                          ? "border-primary/35 bg-primary/10 shadow-lg shadow-primary/5"
                          : "border-transparent bg-transparent",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-background/70 text-muted-foreground group-hover:text-foreground">
                          <TerminalSquare className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-mono text-sm font-semibold text-foreground">{node.address}</p>
                            <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                              <StatusDot status={node.status} />
                              {t(`status.${node.status}`)}
                            </span>
                          </div>
                          <p className="mt-1 truncate text-sm font-medium text-foreground">{label}</p>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">{group}</p>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {node.tags.map((tag) => (
                              <ConnectionTag key={tag} tag={tag} />
                            ))}
                          </div>
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

          {selectedNode ? (
            <section className="grid gap-5">
              <Card className="overflow-hidden border-border/70 bg-card/85 py-0 shadow-xl shadow-foreground/5 backdrop-blur">
                <CardContent className="p-0">
                  <div className="border-b border-border/70 bg-[linear-gradient(135deg,hsl(var(--muted)/0.8),transparent)] p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-background/80 text-foreground">
                          <TerminalSquare className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="truncate font-mono text-lg font-semibold tracking-tight text-foreground">
                              {selectedNode.address}
                            </h2>
                            <Badge
                              variant="outline"
                              className={cn("rounded-full border px-2.5 py-1", statusBorderClassNames[selectedNode.status])}
                            >
                              <StatusDot status={selectedNode.status} className="h-2 w-2 shadow-none" />
                              {t(`status.${selectedNode.status}`)}
                            </Badge>
                          </div>
                          <p className="mt-1 text-sm font-medium text-foreground">
                            {getDemoConnectionText(selectedNode.label, locale)}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {getDemoConnectionText(selectedNode.group, locale)}
                          </p>
                        </div>
                      </div>
                      <Badge variant="secondary" className="rounded-full px-3 py-1">
                        {t("detail.currentContext")}
                      </Badge>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {selectedNode.tags.map((tag) => (
                        <ConnectionTag key={tag} tag={tag} />
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-5 p-5">
                    <DetailSection title={t("sections.general")}>
                      <DetailGrid>
                        <DetailItem label={t("fields.address")} value={selectedNode.address} mono />
                        <DetailItem label={t("fields.group")} value={getDemoConnectionText(selectedNode.group, locale)} />
                        <DetailItem label={t("fields.status")} value={t(`status.${selectedNode.status}`)} />
                      </DetailGrid>
                      {selectedNode.issue ? (
                        <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                          {getDemoConnectionText(selectedNode.issue, locale)}
                        </div>
                      ) : null}
                    </DetailSection>

                    <DetailSection title={t("sections.ssh")}>
                      <DetailGrid>
                        <DetailItem label={t("fields.port")} value={String(selectedNode.ssh.port)} mono />
                        <DetailItem label={t("fields.username")} value={selectedNode.ssh.username} mono />
                        <DetailItem label={t("fields.auth")} value={t(`auth.${selectedNode.ssh.auth}`)} />
                      </DetailGrid>
                    </DetailSection>

                    <DetailSection title={t("sections.agentContext")}>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <TokenPanel title={t("fields.skills")} values={selectedNode.skills} empty={t("empty.skills")} />
                        <TokenPanel title={t("fields.paths")} values={selectedNode.paths} empty={t("empty.paths")} mono />
                        <TokenPanel
                          title={t("fields.apis")}
                          values={selectedNode.apis.map((api) => `${api.name} · ${api.baseUrl}`)}
                          empty={t("empty.apis")}
                          mono
                        />
                        <TokenPanel
                          title={t("fields.environmentVariables")}
                          values={selectedNode.environmentVariables}
                          empty={t("empty.environmentVariables")}
                          mono
                        />
                      </div>
                      <TextPanel
                        title={t("fields.prompt")}
                        value={selectedNode.prompts.map((prompt) => getDemoConnectionText(prompt, locale)).join("\n")}
                        empty={t("empty.prompt")}
                      />
                      <TextPanel
                        title={t("fields.startupSnippet")}
                        value={selectedNode.startupSnippet}
                        empty={t("empty.startupSnippet")}
                        mono
                      />
                    </DetailSection>
                  </div>
                </CardContent>
              </Card>

              <div className="rounded-3xl border border-dashed border-border/80 bg-muted/25 p-4 text-sm leading-6 text-muted-foreground">
                {t("demoOnly")}
              </div>
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
        className="min-h-24 resize-none"
      />
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  )
}

function DetailGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-3">{children}</div>
}

function DetailItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-1 truncate text-sm font-medium text-foreground", mono && "font-mono")}>{value}</p>
    </div>
  )
}

function TokenPanel({
  title,
  values,
  empty,
  mono = false,
}: {
  title: string
  values: string[]
  empty: string
  mono?: boolean
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-muted/25 p-4">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {values.length > 0 ? (
          values.map((value) => (
            <span
              key={value}
              className={cn(
                "rounded-full border border-border/70 bg-background/70 px-2.5 py-1 text-xs text-foreground",
                mono && "font-mono",
              )}
            >
              {value}
            </span>
          ))
        ) : (
          <span className="text-sm text-muted-foreground">{empty}</span>
        )}
      </div>
    </div>
  )
}

function TextPanel({
  title,
  value,
  empty,
  mono = false,
}: {
  title: string
  value: string
  empty: string
  mono?: boolean
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-muted/25 p-4">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{title}</p>
      <pre
        className={cn(
          "mt-3 whitespace-pre-wrap break-words rounded-xl bg-background/70 p-3 text-sm leading-6 text-foreground",
          mono ? "font-mono" : "font-sans",
        )}
      >
        {value || empty}
      </pre>
    </div>
  )
}
