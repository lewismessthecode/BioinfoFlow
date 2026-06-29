"use client"

import {
  type ChangeEvent,
  type Dispatch,
  type DragEvent,
  type FormEvent,
  type ReactNode,
  type RefObject,
  type SetStateAction,
} from "react"
import { BookOpenText, CheckCircle2, FileText, KeyRound, Server, Upload } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
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
export type FormErrorField = "port" | "ssh_alias" | "key_path" | null

export const initialConnectionForm: ConnectionFormState = {
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

type ConnectionDialogProps = {
  open: boolean
  mode: DialogMode
  form: ConnectionFormState
  formError: string | null
  formErrorField: FormErrorField
  skillDragActive: boolean
  isSaving: boolean
  skillFileInputRef: RefObject<HTMLInputElement | null>
  onOpenChange: (open: boolean) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onFormChange: Dispatch<SetStateAction<ConnectionFormState>>
  onSkillDragActiveChange: (active: boolean) => void
  onSkillDrop: (event: DragEvent<HTMLDivElement>) => void
  onSkillFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  onAppendSkillText: (text: string) => void
}

export function ConnectionDialog({
  open,
  mode,
  form,
  formError,
  formErrorField,
  skillDragActive,
  isSaving,
  skillFileInputRef,
  onOpenChange,
  onSubmit,
  onFormChange,
  onSkillDragActiveChange,
  onSkillDrop,
  onSkillFileChange,
  onAppendSkillText,
}: ConnectionDialogProps) {
  const t = useTranslations("connections")
  const tCommon = useTranslations("common")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[min(92vh,780px)] overflow-hidden rounded-[24px] border-border/60 bg-card/95 p-0 text-card-foreground shadow-2xl shadow-foreground/15 sm:max-w-3xl">
        <form onSubmit={onSubmit} noValidate className="flex max-h-[min(92vh,780px)] flex-col">
          <DialogHeader className="border-b border-border/60 px-5 py-4">
            <DialogTitle>{mode === "edit" ? t("dialog.editTitle") : t("dialog.title")}</DialogTitle>
            <DialogDescription>{t("dialog.description")}</DialogDescription>
          </DialogHeader>

          <div className="grid min-h-0 flex-1 gap-3 overflow-y-auto px-5 py-4">
            <div className="grid content-start gap-3">
              <section className="grid gap-3 rounded-[18px] border border-border/60 bg-background/55 p-3.5">
                <FormSectionTitle title={t("sections.connection")} icon={<Server className="h-4 w-4" />} />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={t("fields.name")} htmlFor="connection-name">
                    <Input
                      id="connection-name"
                      value={form.name}
                      onChange={(event) => onFormChange((current) => ({ ...current, name: event.target.value }))}
                      placeholder={t("form.placeholders.name")}
                    />
                  </Field>
                  <Field label={t("fields.host")} htmlFor="connection-host">
                    <Input
                      id="connection-host"
                      value={form.host}
                      onChange={(event) => onFormChange((current) => ({ ...current, host: event.target.value }))}
                      placeholder={t("form.placeholders.host")}
                      required
                    />
                  </Field>
                </div>
                <div
                  className={cn(
                    "grid gap-3",
                    form.auth_method === "ssh_config"
                      ? "sm:grid-cols-[minmax(84px,0.55fr)_minmax(0,1fr)_minmax(0,1fr)]"
                      : "sm:grid-cols-[minmax(84px,0.55fr)_minmax(0,1fr)]",
                  )}
                >
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
                  <Field label={t("fields.username")} htmlFor="connection-username">
                    <Input
                      id="connection-username"
                      value={form.username}
                      onChange={(event) => onFormChange((current) => ({ ...current, username: event.target.value }))}
                      placeholder={t("form.placeholders.username")}
                    />
                  </Field>
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
                </div>
                {form.auth_method === "ssh_config" ? (
                  <p className="text-xs leading-5 text-muted-foreground">{t("form.sshConfigNote")}</p>
                ) : null}
              </section>

              <section className="grid gap-3 rounded-[18px] border border-border/60 bg-background/55 p-3.5">
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
                        onFormChange((current) => ({
                          ...current,
                          auth_method: method,
                          key_path: method === "key_file" ? current.key_path : "",
                        }))
                      }
                    />
                  ))}
                </div>
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
                <p className="text-xs leading-5 text-muted-foreground">{t("form.secretsNote")}</p>
              </section>
            </div>

            <section className="grid content-start gap-3 rounded-2xl border border-border/60 bg-background/55 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <FormSectionTitle title={t("sections.agentSkill")} icon={<BookOpenText className="h-4 w-4" />} />
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button type="button" variant="outline" size="sm" className="h-8 rounded-full">
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
              <TextFieldArea
                id="connection-skill-instructions"
                label={t("fields.skillInstructions")}
                value={form.skill_instructions}
                onChange={(value) => onFormChange((current) => ({ ...current, skill_instructions: value }))}
                placeholder={t("form.placeholders.skillInstructions")}
              />
              <button
                type="button"
                aria-label={t("skillDrop.title")}
                onClick={() => skillFileInputRef.current?.click()}
                onDragEnter={(event) => {
                  event.preventDefault()
                  onSkillDragActiveChange(true)
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => onSkillDragActiveChange(false)}
                onDrop={onSkillDrop}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-xl border border-dashed px-3 py-2 text-left text-sm text-muted-foreground transition focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                  skillDragActive ? "border-primary/60 bg-primary/10 text-foreground" : "border-border bg-muted/20",
                )}
              >
                <Upload className="h-4 w-4" />
                <span>
                  <span className="block font-medium text-foreground">{t("skillDrop.title")}</span>
                  <span className="block text-xs">{t("skillDrop.hint")}</span>
                </span>
              </button>
              <input
                ref={skillFileInputRef}
                type="file"
                accept=".txt,.md,.markdown,text/plain,text/markdown"
                className="sr-only"
                onChange={onSkillFileChange}
              />
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
          <DialogFooter className="border-t border-border/60 bg-muted/10 px-5 py-3">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? t("dialog.saving") : mode === "edit" ? t("dialog.save") : t("dialog.add")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
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

function FormSectionTitle({ title, icon }: { title: string; icon: ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
      <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border/60 bg-background/70 text-muted-foreground">
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
        "min-h-[4.5rem] rounded-[18px] border p-2.5 text-left transition hover:border-foreground/20 hover:bg-background/80",
        selected ? "border-foreground/25 bg-background shadow-sm shadow-foreground/5" : "border-border/60 bg-background/50",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        {selected ? <CheckCircle2 className="h-4 w-4 text-foreground" /> : null}
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
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      <Textarea
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-h-28 resize-none border-border/60 bg-background/70 lg:min-h-32"
      />
    </div>
  )
}
