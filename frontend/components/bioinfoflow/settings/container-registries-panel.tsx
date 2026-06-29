"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react"
import { Loader2, PlayCircle, Plus, Star, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { ContainerRegistryConfig } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useTranslations } from "next-intl"

type CredentialSource = "none" | "env" | "stored"

type RegistryForm = {
  id: string | null
  name: string
  endpoint: string
  namespace: string
  insecure: boolean
  is_default: boolean
  credential_source: CredentialSource
  env_username_var: string
  env_password_var: string
  username: string
  password: string
}

const EMPTY_FORM: RegistryForm = {
  id: null,
  name: "",
  endpoint: "",
  namespace: "",
  insecure: false,
  is_default: false,
  credential_source: "none",
  env_username_var: "",
  env_password_var: "",
  username: "",
  password: "",
}

type TestResult = {
  success: boolean
  status: string
  error?: string | null
}

export function ContainerRegistriesPanel() {
  const t = useTranslations("settings")
  const tRef = useRef(t)
  const [registries, setRegistries] = useState<ContainerRegistryConfig[]>([])
  const [form, setForm] = useState<RegistryForm>(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const editing = Boolean(form.id)
  const credentialsReady =
    form.credential_source === "none" ||
    (form.credential_source === "env" &&
      form.env_username_var.trim().length > 0 &&
      form.env_password_var.trim().length > 0) ||
    (form.credential_source === "stored" &&
      ((editing && !form.username.trim() && !form.password) ||
        (form.username.trim().length > 0 && form.password.length > 0)))
  const canSave =
    form.name.trim().length > 0 &&
    form.endpoint.trim().length > 0 &&
    credentialsReady
  const sortedRegistries = useMemo(
    () =>
      [...registries].sort((a, b) => {
        if (a.is_default && !b.is_default) return -1
        if (!a.is_default && b.is_default) return 1
        return String(a.name ?? a.endpoint ?? "").localeCompare(
          String(b.name ?? b.endpoint ?? ""),
        )
      }),
    [registries],
  )

  useEffect(() => {
    tRef.current = t
  }, [t])

  const loadRegistries = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await apiRequest<ContainerRegistryConfig[]>("/container-registries")
      setRegistries(data)
    } catch (error) {
      toast.error(getApiErrorMessage(error, tRef.current("registries.loadFailed")))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRegistries()
  }, [loadRegistries])

  const resetForm = () => {
    setForm(EMPTY_FORM)
  }

  const editRegistry = (registry: ContainerRegistryConfig) => {
    setForm({
      id: registry.id ?? null,
      name: registry.name ?? "",
      endpoint: registry.endpoint ?? registry.registry ?? registry.host ?? registry.url ?? "",
      namespace: registry.namespace ?? "",
      insecure: Boolean(registry.insecure),
      is_default: Boolean(registry.is_default),
      credential_source: resolveCredentialSource(registry.credential_source),
      env_username_var: registry.env_username_var ?? "",
      env_password_var: registry.env_password_var ?? "",
      username: "",
      password: "",
    })
  }

  const saveRegistry = async () => {
    if (!canSave) return
    setSaving(true)
    try {
      const payload = buildRegistryPayload(form)
      if (form.id) {
        await apiRequest(`/container-registries/${form.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        })
        toast.success(t("registries.saved"))
      } else {
        await apiRequest("/container-registries", {
          method: "POST",
          body: JSON.stringify(payload),
        })
        toast.success(t("registries.created"))
      }
      resetForm()
      await loadRegistries()
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("registries.saveFailed")))
    } finally {
      setSaving(false)
    }
  }

  const testRegistry = async (registryId: string) => {
    setTestingId(registryId)
    try {
      const { data } = await apiRequest<TestResult>(
        `/container-registries/${registryId}/test`,
        { method: "POST" },
      )
      if (data.success) {
        toast.success(t("registries.testOk"))
      } else {
        toast.error(data.error || t("registries.testFailed"))
      }
      await loadRegistries()
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("registries.testFailed")))
    } finally {
      setTestingId(null)
    }
  }

  const makeDefault = async (registryId: string) => {
    try {
      await apiRequest(`/container-registries/${registryId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_default: true }),
      })
      toast.success(t("registries.defaultSaved"))
      await loadRegistries()
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("registries.saveFailed")))
    }
  }

  const deleteRegistry = async (registry: ContainerRegistryConfig) => {
    if (!registry.id) return
    if (!window.confirm(t("registries.deleteConfirm", { name: registry.name ?? registry.endpoint ?? registry.id }))) {
      return
    }
    setDeletingId(registry.id)
    try {
      await apiRequest(`/container-registries/${registry.id}`, { method: "DELETE" })
      toast.success(t("registries.deleted"))
      if (form.id === registry.id) resetForm()
      await loadRegistries()
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("registries.deleteFailed")))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-foreground">
          {t("registries.title")}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("registries.description")}
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <div className="space-y-4 rounded-xl border border-border/60 bg-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-foreground">
                {editing ? t("registries.form.editTitle") : t("registries.form.createTitle")}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("registries.form.subtitle")}
              </p>
            </div>
            {editing ? (
              <Button type="button" variant="outline" size="sm" onClick={resetForm}>
                {t("registries.form.new")}
              </Button>
            ) : null}
          </div>

          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="registry-name">{t("registries.fields.name")}</Label>
              <Input
                id="registry-name"
                value={form.name}
                onChange={(event) => setFormField(setForm, "name", event.target.value)}
                placeholder={t("registries.placeholders.name")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="registry-endpoint">{t("registries.fields.endpoint")}</Label>
              <Input
                id="registry-endpoint"
                value={form.endpoint}
                onChange={(event) => setFormField(setForm, "endpoint", event.target.value)}
                placeholder="http://10.227.4.56:80"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="registry-namespace">{t("registries.fields.namespace")}</Label>
              <Input
                id="registry-namespace"
                value={form.namespace}
                onChange={(event) => setFormField(setForm, "namespace", event.target.value)}
                placeholder="pipeline-dev"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2">
                <Label htmlFor="registry-default" className="text-sm">
                  {t("registries.fields.default")}
                </Label>
                <Switch
                  id="registry-default"
                  checked={form.is_default}
                  onCheckedChange={(checked) =>
                    setFormField(setForm, "is_default", Boolean(checked))
                  }
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2">
                <Label htmlFor="registry-insecure" className="text-sm">
                  {t("registries.fields.insecure")}
                </Label>
                <Switch
                  id="registry-insecure"
                  checked={form.insecure}
                  onCheckedChange={(checked) =>
                    setFormField(setForm, "insecure", Boolean(checked))
                  }
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="registry-credentials">{t("registries.fields.credentials")}</Label>
              <select
                id="registry-credentials"
                value={form.credential_source}
                onChange={(event) =>
                  setFormField(
                    setForm,
                    "credential_source",
                    event.target.value as CredentialSource,
                  )
                }
                className="border-input h-10 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
              >
                <option value="none">{t("registries.credentials.none")}</option>
                <option value="env">{t("registries.credentials.env")}</option>
                <option value="stored">{t("registries.credentials.stored")}</option>
              </select>
            </div>

            {form.credential_source === "env" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="registry-env-user">{t("registries.fields.envUsername")}</Label>
                  <Input
                    id="registry-env-user"
                    value={form.env_username_var}
                    onChange={(event) =>
                      setFormField(setForm, "env_username_var", event.target.value)
                    }
                    placeholder="BIO_REGISTRY_USER"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="registry-env-password">{t("registries.fields.envPassword")}</Label>
                  <Input
                    id="registry-env-password"
                    value={form.env_password_var}
                    onChange={(event) =>
                      setFormField(setForm, "env_password_var", event.target.value)
                    }
                    placeholder="BIO_REGISTRY_PASSWORD"
                  />
                </div>
              </div>
            ) : null}

            {form.credential_source === "stored" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="registry-username">{t("registries.fields.username")}</Label>
                  <Input
                    id="registry-username"
                    value={form.username}
                    onChange={(event) =>
                      setFormField(setForm, "username", event.target.value)
                    }
                    placeholder={t("registries.placeholders.username")}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="registry-password">{t("registries.fields.password")}</Label>
                  <Input
                    id="registry-password"
                    type="password"
                    value={form.password}
                    onChange={(event) =>
                      setFormField(setForm, "password", event.target.value)
                    }
                    placeholder={t("registries.placeholders.password")}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <Button
            type="button"
            className="w-full gap-2"
            disabled={!canSave || saving}
            onClick={() => void saveRegistry()}
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
            {editing ? t("registries.form.save") : t("registries.form.create")}
          </Button>
        </div>

        <div className="space-y-3">
          {loading ? (
            <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-card p-4 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {t("registries.loading")}
            </div>
          ) : sortedRegistries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-card p-6 text-sm text-muted-foreground">
              {t("registries.empty")}
            </div>
          ) : (
            sortedRegistries.map((registry) => (
              <RegistryRow
                key={registry.id ?? registry.endpoint ?? registry.name}
                registry={registry}
                testing={testingId === registry.id}
                deleting={deletingId === registry.id}
                onEdit={editRegistry}
                onTest={(id) => void testRegistry(id)}
                onDefault={(id) => void makeDefault(id)}
                onDelete={(item) => void deleteRegistry(item)}
              />
            ))
          )}
        </div>
      </div>
    </section>
  )
}

function RegistryRow({
  registry,
  testing,
  deleting,
  onEdit,
  onTest,
  onDefault,
  onDelete,
}: {
  registry: ContainerRegistryConfig
  testing: boolean
  deleting: boolean
  onEdit: (registry: ContainerRegistryConfig) => void
  onTest: (id: string) => void
  onDefault: (id: string) => void
  onDelete: (registry: ContainerRegistryConfig) => void
}) {
  const t = useTranslations("settings")
  const endpoint = registry.endpoint ?? registry.registry ?? registry.host ?? registry.url ?? ""
  const status = registry.last_status ?? "untested"
  const registryId = registry.id ?? null

  return (
    <div className="rounded-xl border border-border/60 bg-card p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="truncate text-sm font-semibold text-foreground">
              {registry.name || endpoint}
            </h4>
            {registry.is_default ? (
              <span className="inline-flex h-6 items-center gap-1 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 text-xs font-medium text-amber-700 dark:text-amber-300">
                <Star className="size-3" />
                {t("registries.defaultBadge")}
              </span>
            ) : null}
            <span
              className={cn(
                "inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium",
                status === "ok"
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : status === "error"
                    ? "border-destructive/25 bg-destructive/10 text-destructive"
                    : "border-border bg-muted text-muted-foreground",
              )}
            >
              {t(`registries.status.${status === "ok" || status === "error" ? status : "untested"}`)}
            </span>
          </div>
          <p className="mt-1 truncate text-sm text-muted-foreground">
            {endpoint}
            {registry.namespace ? `/${registry.namespace}` : ""}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t(`registries.credentials.${resolveCredentialSource(registry.credential_source)}`)}
            {registry.username_hint ? ` · ${registry.username_hint}` : ""}
          </p>
          {registry.last_error ? (
            <p className="mt-2 text-xs text-destructive">{registry.last_error}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          <Button type="button" variant="outline" size="sm" onClick={() => onEdit(registry)}>
            {t("registries.actions.edit")}
          </Button>
          {registryId ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-2"
                disabled={testing}
                onClick={() => onTest(registryId)}
              >
                {testing ? <Loader2 className="size-3.5 animate-spin" /> : <PlayCircle className="size-3.5" />}
                {t("registries.actions.test")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={Boolean(registry.is_default)}
                onClick={() => onDefault(registryId)}
              >
                {t("registries.actions.makeDefault")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-2 text-destructive hover:text-destructive"
                disabled={deleting}
                onClick={() => onDelete(registry)}
              >
                {deleting ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                {t("registries.actions.delete")}
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function setFormField<K extends keyof RegistryForm>(
  setForm: Dispatch<SetStateAction<RegistryForm>>,
  key: K,
  value: RegistryForm[K],
) {
  setForm((current) => ({ ...current, [key]: value }))
}

function buildRegistryPayload(form: RegistryForm) {
  const payload: Record<string, unknown> = {
    name: form.name.trim(),
    endpoint: form.endpoint.trim(),
    namespace: form.namespace.trim() || null,
    insecure: form.insecure,
    is_default: form.is_default,
    credential_source: form.credential_source,
  }

  if (form.credential_source === "env") {
    payload.env_username_var = form.env_username_var.trim()
    payload.env_password_var = form.env_password_var.trim()
  } else if (form.credential_source === "stored") {
    if (form.username.trim()) payload.username = form.username.trim()
    if (form.password) payload.password = form.password
  }

  return payload
}

function resolveCredentialSource(value: unknown): CredentialSource {
  return value === "env" || value === "stored" ? value : "none"
}
