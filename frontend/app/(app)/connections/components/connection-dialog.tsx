"use client"

import {
  type Dispatch,
  type FormEvent,
  type ReactNode,
  type SetStateAction,
} from "react"
import { BookOpenText, CheckCircle2, FileText, KeyRound, Server, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { RemoteConnectionAuthMethod } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

export type ConnectionFormState = {
  name: string
  host: string
  port: string
  username: string
  auth_method: RemoteConnectionAuthMethod
  ssh_alias: string
  key_path: string
  skill_instructions: string
}

export type DialogMode = "create" | "edit"
export type FormErrorField = "host" | "port" | "ssh_alias" | "key_path" | null

export const initialConnectionForm: ConnectionFormState = {
  name: "",
  host: "",
  port: "22",
  username: "",
  auth_method: "agent",
  ssh_alias: "",
  key_path: "",
  skill_instructions: "",
}

const authMethods: RemoteConnectionAuthMethod[] = ["agent", "key_file", "ssh_config"]
const skillPresetKeys = ["nextflowHpc", "slurmDiagnostics", "readonlyInspection"] as const

type ConnectionDialogProps = {
  open: boolean
  mode: DialogMode
  form: ConnectionFormState
  formError: string | null
  formErrorField: FormErrorField
  isSaving: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onFormChange: Dispatch<SetStateAction<ConnectionFormState>>
  onAppendSkillText: (text: string) => void
}

export function ConnectionDialog({
  open,
  mode,
  form,
  formError,
  formErrorField,
  isSaving,
  onOpenChange,
  onSubmit,
  onFormChange,
  onAppendSkillText,
}: ConnectionDialogProps) {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")

  if (!open) return null

  return (
    <aside
      role="complementary"
      aria-label={t("dialog.panelLabel")}
      className="min-h-0 overflow-hidden rounded-[32px] border border-border/70 bg-card/95 shadow-lg shadow-foreground/10 lg:sticky lg:top-7 lg:max-h-[calc(100vh-3.5rem)]"
    >
      <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-col lg:max-h-[calc(100vh-3.5rem)]">
        <div className="flex items-start justify-between gap-4 border-b border-border/60 bg-background/45 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight text-foreground">
              {mode === "edit" ? t("dialog.editTitle") : t("dialog.title")}
            </h2>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 rounded-full"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
            aria-label={tCommon("close")}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid gap-4">
            <PanelSection title={t("sections.address")} icon={<Server className="h-4 w-4" />}>
              <div className="grid grid-cols-[56px_minmax(0,1fr)] gap-3">
                <div className="flex h-14 w-14 items-center justify-center rounded-[20px] border border-border/70 bg-background/75 text-muted-foreground shadow-sm shadow-foreground/5">
                  <Server className="h-6 w-6" />
                </div>
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
              </div>
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
                <Field label={t("fields.username")} htmlFor="connection-username">
                  <Input
                    id="connection-username"
                    value={form.username}
                    onChange={(event) => onFormChange((current) => ({ ...current, username: event.target.value }))}
                    placeholder={t("form.placeholders.username")}
                  />
                </Field>

                <div className="grid gap-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">{t("fields.auth")}</Label>
                  <div aria-label={t("fields.auth")} className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
                    {authMethods.map((method) => (
                      <AuthMethodButton
                        key={method}
                        selected={form.auth_method === method}
                        title={t(`auth.${method}`)}
                        onSelect={() =>
                          onFormChange((current) => ({
                            ...current,
                            auth_method: method,
                            ssh_alias: method === "ssh_config" ? current.ssh_alias : "",
                            key_path: method === "key_file" ? current.key_path : "",
                          }))
                        }
                      />
                    ))}
                  </div>
                </div>

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
                  className="min-h-36 resize-none border-border/60 bg-background/70"
                />
              </div>
            </PanelSection>
          </div>
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

        <div className="flex justify-end gap-2 border-t border-border/60 bg-background/45 px-5 py-3">
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
    <section className="grid gap-3 rounded-[22px] border border-border/60 bg-background/55 p-4">
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
    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
      {icon ? (
        <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border/60 bg-background/70 text-muted-foreground">
          {icon}
        </span>
      ) : null}
      {title}
    </div>
  )
}

function AuthMethodButton({
  selected,
  title,
  onSelect,
}: {
  selected: boolean
  title: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        "inline-flex min-h-10 items-center justify-between gap-2 rounded-2xl border px-3 py-2 text-left text-sm font-medium transition hover:border-foreground/20 hover:bg-background/80",
        selected ? "border-primary/35 bg-background text-foreground shadow-sm shadow-foreground/5 ring-4 ring-primary/10" : "border-border/60 bg-background/50 text-muted-foreground",
      )}
    >
      <span>{title}</span>
      {selected ? <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" /> : null}
    </button>
  )
}
