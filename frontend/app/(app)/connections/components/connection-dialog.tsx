"use client"

import {
  type ChangeEvent,
  type Dispatch,
  type FormEvent,
  type ReactNode,
  type SetStateAction,
} from "react"
import {
  BookOpenText,
  CheckCircle2,
  CircleAlert,
  FileText,
  KeyRound,
  MoreHorizontal,
  Play,
  RefreshCw,
  Server,
  TerminalSquare,
  Trash2,
  X,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
import type { RemoteConnection, RemoteConnectionAuthMethod } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

import { TextPanel } from "./connection-ui"

export type ConnectionFormState = {
  name: string
  host: string
  port: string
  username: string
  auth_method: RemoteConnectionAuthMethod
  jump_connection_id: string
  ssh_alias: string
  key_path: string
  password: string
  private_key: string
  passphrase: string
  skill_instructions: string
}

export type DialogMode = "create" | "edit"
export type FormErrorField =
  | "host"
  | "port"
  | "ssh_alias"
  | "key_path"
  | "password"
  | "private_key"
  | "jump_connection_id"
  | null

export const initialConnectionForm: ConnectionFormState = {
  name: "",
  host: "",
  port: "22",
  username: "",
  auth_method: "password",
  jump_connection_id: "",
  ssh_alias: "",
  key_path: "",
  password: "",
  private_key: "",
  passphrase: "",
  skill_instructions: "",
}

const primaryAuthMethods: RemoteConnectionAuthMethod[] = ["password", "private_key"]
const advancedAuthMethods: RemoteConnectionAuthMethod[] = ["agent", "key_file", "ssh_config"]
const skillPresetKeys = ["nextflowHpc", "slurmDiagnostics", "readonlyInspection"] as const

type ConnectionDialogProps = {
  open: boolean
  mode: DialogMode
  connection: RemoteConnection | null
  testing: boolean
  probing: boolean
  probeOutput: string
  probeFeedback: {
    status: "running" | "success" | "error"
    message: string
  } | null
  form: ConnectionFormState
  formError: string | null
  formErrorField: FormErrorField
  isSaving: boolean
  jumpCandidates: RemoteConnection[]
  onOpenChange: (open: boolean) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onFormChange: Dispatch<SetStateAction<ConnectionFormState>>
  onAppendSkillText: (text: string) => void
  onTest: (connection: RemoteConnection) => void
  onRunProbe: (connection: RemoteConnection) => void
  onDelete: (connection: RemoteConnection) => void
}

export function ConnectionDialog({
  open,
  mode,
  connection,
  testing,
  probing,
  probeOutput,
  probeFeedback,
  form,
  formError,
  formErrorField,
  isSaving,
  jumpCandidates,
  onOpenChange,
  onSubmit,
  onFormChange,
  onAppendSkillText,
  onTest,
  onRunProbe,
  onDelete,
}: ConnectionDialogProps) {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")
  const usesAdvancedAuth = advancedAuthMethods.includes(form.auth_method)
  const usesJumpHost = form.auth_method === "jump"

  const handlePrivateKeyFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : ""
      onFormChange((current) => ({ ...current, private_key: value }))
    }
    reader.readAsText(file)
    event.target.value = ""
  }

  const selectAuthMethod = (method: RemoteConnectionAuthMethod) => {
    onFormChange((current) => ({
      ...current,
      auth_method: method,
      jump_connection_id: "",
      ssh_alias: method === "ssh_config" ? current.ssh_alias : "",
      key_path: method === "key_file" ? current.key_path : "",
      password: method === "password" ? current.password : "",
      private_key: method === "private_key" ? current.private_key : "",
      passphrase: method === "private_key" ? current.passphrase : "",
    }))
  }

  const selectRoute = (route: "direct" | "jump") => {
    onFormChange((current) => {
      if (route === "direct" && current.auth_method !== "jump") return current
      if (route === "jump" && current.auth_method === "jump") return current

      return {
        ...current,
        auth_method: route === "jump" ? "jump" : "password",
        jump_connection_id: "",
        ssh_alias: "",
        key_path: "",
        password: "",
        private_key: "",
        passphrase: "",
      }
    })
  }

  if (!open) return null

  return (
    <aside
      role="complementary"
      aria-label={t("dialog.panelLabel")}
      className="absolute inset-y-0 right-0 z-30 flex min-h-0 w-full animate-in flex-col slide-in-from-right overflow-hidden border-l border-border/60 bg-background shadow-2xl shadow-foreground/10 duration-200 motion-reduce:animate-none sm:w-[min(100vw,420px)] lg:w-[360px] xl:w-[376px]"
    >
      <form onSubmit={onSubmit} noValidate className="flex h-full min-h-0 w-full flex-col">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border/60 bg-background/95 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {mode === "edit" ? t("dialog.editTitle") : t("dialog.title")}
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {mode === "edit" && connection ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-full"
                    aria-label={tCommon("actions")}
                    disabled={isSaving}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem disabled={testing} onSelect={() => onTest(connection)}>
                    <RefreshCw className={cn("h-4 w-4", testing && "animate-spin")} />
                    {testing ? t("actions.testing") : t("actions.retestConnection")}
                  </DropdownMenuItem>
                  <DropdownMenuItem disabled={probing} onSelect={() => onRunProbe(connection)}>
                    <Play className="h-4 w-4" />
                    {probing ? t("actions.runningProbe") : t("actions.runProbe")}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => onDelete(connection)}>
                    <Trash2 className="h-4 w-4" />
                    {t("actions.deleteConnection")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full"
              onClick={() => onOpenChange(false)}
              disabled={isSaving}
              aria-label={tCommon("close")}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {probeFeedback ? (
          <div
            role={probeFeedback.status === "error" ? "alert" : "status"}
            aria-live={probeFeedback.status === "error" ? "assertive" : "polite"}
            className={cn(
              "mx-3 mt-3 flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-sm",
              probeFeedback.status === "running" && "border-primary/20 bg-primary/5 text-primary",
              probeFeedback.status === "success" && "border-success-border bg-success-muted text-success-foreground",
              probeFeedback.status === "error" && "border-destructive/25 bg-destructive/10 text-destructive",
            )}
          >
            {probeFeedback.status === "running" ? (
              <RefreshCw className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" />
            ) : probeFeedback.status === "success" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            ) : (
              <CircleAlert className="h-4 w-4 shrink-0" />
            )}
            <span>{probeFeedback.message}</span>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 [scrollbar-gutter:stable]">
          <div className="grid gap-3">
            <PanelSection title={t("sections.address")} icon={<Server className="h-4 w-4" />}>
              <Field label={t("fields.host")} htmlFor="connection-host">
                <Input
                  id="connection-host"
                  value={form.host}
                  onChange={(event) => onFormChange((current) => ({ ...current, host: event.target.value }))}
                  placeholder={t("form.placeholders.host")}
                  required={form.auth_method !== "ssh_config"}
                  aria-invalid={formErrorField === "host"}
                  aria-describedby={formErrorField === "host" ? "connection-form-error" : undefined}
                />
              </Field>
            </PanelSection>

            <PanelSection title={t("sections.general")}>
              <Field label={t("fields.name")} htmlFor="connection-name">
                <Input
                  id="connection-name"
                  value={form.name}
                  onChange={(event) => onFormChange((current) => ({ ...current, name: event.target.value }))}
                  placeholder={t("form.placeholders.name")}
                />
              </Field>
            </PanelSection>

            <PanelSection title={t("sections.sshPort")}>
              <Field label={t("fields.port")} htmlFor="connection-port">
                <Input
                  id="connection-port"
                  value={form.port}
                  inputMode="numeric"
                  onChange={(event) => onFormChange((current) => ({ ...current, port: event.target.value }))}
                  aria-invalid={formErrorField === "port"}
                  aria-describedby={formErrorField === "port" ? "connection-form-error" : undefined}
                />
              </Field>
            </PanelSection>

            <PanelSection title={t("sections.credentials")} icon={<KeyRound className="h-4 w-4" />}>
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">
                    {t("route.label")}
                  </Label>
                  <div aria-label={t("route.label")} className="grid grid-cols-2 gap-2">
                    <AuthMethodButton
                      selected={!usesJumpHost}
                      title={t("route.direct")}
                      onSelect={() => selectRoute("direct")}
                    />
                    <AuthMethodButton
                      selected={usesJumpHost}
                      title={t("route.jump")}
                      onSelect={() => selectRoute("jump")}
                    />
                  </div>
                </div>

                <Field label={t("fields.username")} htmlFor="connection-username">
                  <Input
                    id="connection-username"
                    value={form.username}
                    onChange={(event) => onFormChange((current) => ({ ...current, username: event.target.value }))}
                    placeholder={t("form.placeholders.username")}
                  />
                </Field>

                {usesJumpHost ? (
                  <div className="grid gap-2">
                    {jumpCandidates.length > 0 ? (
                      <Field label={t("route.selector")} htmlFor="connection-jump-host">
                        <Select
                          value={form.jump_connection_id || undefined}
                          onValueChange={(value) =>
                            onFormChange((current) => ({ ...current, jump_connection_id: value }))
                          }
                        >
                          <SelectTrigger
                            id="connection-jump-host"
                            className="w-full"
                            aria-invalid={formErrorField === "jump_connection_id"}
                            aria-describedby={
                              formErrorField === "jump_connection_id" ? "connection-form-error" : undefined
                            }
                          >
                            <SelectValue placeholder={t("route.placeholder")} />
                          </SelectTrigger>
                          <SelectContent>
                            {jumpCandidates.map((candidate) => (
                              <SelectItem key={candidate.id} value={candidate.id}>
                                {candidate.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    ) : (
                      <p role="status" className="rounded-md border border-dashed border-border/60 px-3 py-2 text-xs leading-5 text-muted-foreground">
                        {t("route.noCandidates")}
                      </p>
                    )}
                    <p className="text-xs leading-5 text-muted-foreground">{t("route.helper")}</p>
                  </div>
                ) : (
                <div className="grid gap-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">{t("fields.auth")}</Label>
                  <div aria-label={t("fields.auth")} className="grid gap-2">
                    {primaryAuthMethods.map((method) => (
                      <AuthMethodButton
                        key={method}
                        selected={form.auth_method === method}
                        title={t(`auth.${method}`)}
                        description={t(`authDescriptions.${method}`)}
                        onSelect={() => selectAuthMethod(method)}
                      />
                    ))}
                  </div>
                </div>
                )}

                {!usesJumpHost && form.auth_method === "password" ? (
                  <Field label={t("fields.password")} htmlFor="connection-password">
                    <Input
                      id="connection-password"
                      type="password"
                      value={form.password}
                      onChange={(event) => onFormChange((current) => ({ ...current, password: event.target.value }))}
                      placeholder={t("form.placeholders.password")}
                      required
                      aria-invalid={formErrorField === "password"}
                      aria-describedby={formErrorField === "password" ? "connection-form-error" : undefined}
                    />
                  </Field>
                ) : null}

                {!usesJumpHost && form.auth_method === "private_key" ? (
                  <div className="grid gap-3">
                    <Field label={t("fields.privateKey")} htmlFor="connection-private-key">
                      <Textarea
                        id="connection-private-key"
                        value={form.private_key}
                        onChange={(event) => onFormChange((current) => ({ ...current, private_key: event.target.value }))}
                        placeholder={t("form.placeholders.privateKey")}
                        className="min-h-32 resize-y font-mono text-xs"
                        required
                        aria-invalid={formErrorField === "private_key"}
                        aria-describedby={formErrorField === "private_key" ? "connection-form-error" : undefined}
                      />
                    </Field>
                    <div className="flex items-center justify-between gap-3">
                      <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-border/60 px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/40">
                        <FileText className="h-4 w-4" />
                        {t("actions.uploadPrivateKey")}
                        <input type="file" className="sr-only" onChange={handlePrivateKeyFile} />
                      </label>
                      <Field label={t("fields.passphrase")} htmlFor="connection-passphrase">
                        <Input
                          id="connection-passphrase"
                          type="password"
                          value={form.passphrase}
                          onChange={(event) => onFormChange((current) => ({ ...current, passphrase: event.target.value }))}
                          placeholder={t("form.placeholders.passphrase")}
                        />
                      </Field>
                    </div>
                  </div>
                ) : null}

                {!usesJumpHost ? <details
                  open={usesAdvancedAuth ? true : undefined}
                  className="group grid gap-3 border-t border-border/60 pt-3"
                >
                  <summary className="cursor-pointer list-none text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
                    {t("sections.advancedSsh")}
                  </summary>
                  <div className="grid gap-2 pt-2">
                    {advancedAuthMethods.map((method) => (
                      <AuthMethodButton
                        key={method}
                        selected={form.auth_method === method}
                        title={t(`auth.${method}`)}
                        description={t(`authDescriptions.${method}`)}
                        onSelect={() => selectAuthMethod(method)}
                      />
                    ))}
                  </div>
                </details> : null}

                {form.auth_method === "ssh_config" ? (
                  <Field label={t("fields.sshAlias")} htmlFor="connection-ssh-alias">
                    <Input
                      id="connection-ssh-alias"
                      value={form.ssh_alias}
                      onChange={(event) => onFormChange((current) => ({ ...current, ssh_alias: event.target.value }))}
                      placeholder={t("form.placeholders.sshAlias")}
                      required
                      aria-invalid={formErrorField === "ssh_alias"}
                      aria-describedby={formErrorField === "ssh_alias" ? "connection-form-error" : undefined}
                    />
                  </Field>
                ) : null}

                {form.auth_method === "key_file" ? (
                  <Field label={t("fields.keyPath")} htmlFor="connection-key-path">
                    <Input
                      id="connection-key-path"
                      value={form.key_path}
                      onChange={(event) => onFormChange((current) => ({ ...current, key_path: event.target.value }))}
                      placeholder={t("form.placeholders.keyPath")}
                      required
                      aria-invalid={formErrorField === "key_path"}
                      aria-describedby={formErrorField === "key_path" ? "connection-form-error" : undefined}
                    />
                  </Field>
                ) : null}
              </div>
            </PanelSection>

            <PanelSection title={t("sections.agentSkill")} icon={<BookOpenText className="h-4 w-4" />}>
              <div className="grid gap-3">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="connection-skill-instructions" className="text-xs font-medium text-muted-foreground">
                    {t("fields.skillInstructions")}
                  </Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button type="button" variant="outline" size="sm" className="h-8 rounded-full px-3">
                        <FileText className="h-4 w-4" />
                        {t("actions.insertPreset")}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-56">
                      {skillPresetKeys.map((key) => (
                        <DropdownMenuItem key={key} onSelect={() => onAppendSkillText(t(`skillPresets.${key}.text`))}>
                          {t(`skillPresets.${key}.name`)}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <Textarea
                  id="connection-skill-instructions"
                  value={form.skill_instructions}
                  onChange={(event) => onFormChange((current) => ({ ...current, skill_instructions: event.target.value }))}
                  placeholder={t("form.placeholders.skillInstructions")}
                  className="min-h-28 resize-none border-border/60 bg-background/70"
                />
              </div>
            </PanelSection>

            {mode === "edit" && connection && (probeOutput || probing) ? (
              <PanelSection title={t("probe.description")} icon={<TerminalSquare className="h-4 w-4" />}>
                <TextPanel
                  title={t("probe.titleForConnection", { name: connection.name })}
                  value={probeOutput || t("probe.placeholder")}
                  empty={t("probe.placeholder")}
                />
              </PanelSection>
            ) : null}
          </div>
        </div>

        {formError ? (
          <div
            id="connection-form-error"
            role="alert"
            aria-live="polite"
            className="mx-3 shrink-0 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {formError}
          </div>
        ) : null}

        <div className="flex shrink-0 justify-end gap-2 border-t border-border/60 bg-background/95 px-4 py-3">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            {tCommon("cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("dialog.saving") : mode === "edit" ? t("dialog.save") : t("dialog.add")}
          </Button>
        </div>
      </form>
    </aside>
  )
}

function PanelSection({
  title,
  icon,
  children,
}: {
  title: string
  icon?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="grid gap-3 border-t border-border/60 pt-4 first:border-t-0 first:pt-0">
      <FormSectionTitle title={title} icon={icon} />
      {children}
    </section>
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
      <Label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  )
}

function FormSectionTitle({ title, icon }: { title: string; icon?: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-foreground">
      {icon ? (
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted/50 text-muted-foreground">
          {icon}
        </span>
      ) : null}
      <span className="truncate">{title}</span>
    </div>
  )
}

function AuthMethodButton({
  selected,
  title,
  description,
  onSelect,
}: {
  selected: boolean
  title: string
  description?: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "inline-flex min-h-10 items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors hover:border-foreground/20 hover:bg-muted/30",
        selected ? "border-foreground/40 bg-muted/40 text-foreground" : "border-border/60 bg-transparent text-muted-foreground",
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        {description ? (
          <span className="mt-0.5 block text-xs font-normal leading-4 text-muted-foreground">
            {description}
          </span>
        ) : null}
      </span>
      {selected ? <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" /> : null}
    </button>
  )
}
