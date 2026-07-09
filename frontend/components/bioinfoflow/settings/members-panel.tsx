"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import {
  Ban,
  KeyRound,
  Loader2,
  Shield,
  ShieldCheck,
  UserRound,
} from "@/lib/icons"
import { authClient } from "@/lib/auth-client"
import type { TeamRole } from "@/lib/auth-config"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { toast } from "sonner"

type MemberUser = {
  id: string
  name: string
  email: string
  role?: string | null
  teamRole?: string | null
  banned?: boolean | null
}

type MembersPanelProps = {
  viewerId: string
  viewerRole: TeamRole
  authLocalEnabled: boolean
}

type AuthClientResult<T = unknown> = {
  data?: T | null
  error?: { message?: string } | null
}

type ApiEnvelope<T> =
  | { success: true; data: T }
  | { success: false; error?: { message?: string } }

const ALL_TEAM_ROLES: TeamRole[] = ["owner", "admin", "member"]

function resolveTeamRole(user: MemberUser): TeamRole {
  if (user.teamRole === "owner" || user.teamRole === "admin") {
    return user.teamRole
  }
  if (user.role === "admin") {
    return "admin"
  }
  return "member"
}

function assertAuthSuccess<T>(result: AuthClientResult<T> | undefined): T | null {
  if (!result) {
    return null
  }
  if (result.error) {
    throw new Error(result.error.message || "Auth admin operation failed")
  }
  return result.data ?? null
}

async function requestTeamMembers<T>(
  init?: RequestInit,
): Promise<T> {
  const response = await fetch("/api/team/members", {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
  const payload = (await response.json()) as ApiEnvelope<T>
  if (!response.ok || !payload.success) {
    throw new Error(
      payload.success
        ? "Member operation failed"
        : payload.error?.message || "Member operation failed",
    )
  }
  return payload.data
}

export function MembersPanel({
  viewerId,
  viewerRole,
  authLocalEnabled,
}: MembersPanelProps) {
  const t = useTranslations("settings.members")
  const [members, setMembers] = useState<MemberUser[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [passwordResetUser, setPasswordResetUser] = useState<MemberUser | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [createForm, setCreateForm] = useState({
    name: "",
    email: "",
    password: "",
    teamRole: "member" as TeamRole,
  })
  const [resetPassword, setResetPassword] = useState("")

  const ownerCount = useMemo(
    () => members.filter((member) => resolveTeamRole(member) === "owner").length,
    [members],
  )

  const loadMembers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await requestTeamMembers<{ users?: MemberUser[] }>()
      setMembers(data.users ?? [])
    } catch {
      toast.error(t("loadFailed"))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void loadMembers()
  }, [loadMembers])

  const canManageOwnerRole = viewerRole === "owner"

  const handleCreateUser = async () => {
    setCreating(true)
    setCreateError(null)
    try {
      await requestTeamMembers<{ user: MemberUser }>({
        method: "POST",
        body: JSON.stringify({
          email: createForm.email,
          name: createForm.name,
          password: authLocalEnabled ? createForm.password : undefined,
          teamRole: createForm.teamRole,
        }),
      })
      toast.success(t("created"))
      setCreateOpen(false)
      setCreateForm({
        name: "",
        email: "",
        password: "",
        teamRole: "member",
      })
      await loadMembers()
    } catch (error) {
      const message = error instanceof Error ? error.message : t("createFailed")
      setCreateError(message)
      toast.error(message)
    } finally {
      setCreating(false)
    }
  }

  const handleRoleChange = async (user: MemberUser, nextRole: TeamRole) => {
    if (nextRole === "owner" && !canManageOwnerRole) {
      return
    }
    if (
      resolveTeamRole(user) === "owner" &&
      nextRole !== "owner" &&
      ownerCount <= 1
    ) {
      toast.error(t("lastOwner"))
      return
    }

    setSavingId(user.id)
    try {
      await requestTeamMembers<{ user: MemberUser }>({
        method: "PATCH",
        body: JSON.stringify({
          action: "role",
          userId: user.id,
          teamRole: nextRole,
        }),
      })
      toast.success(t("roleUpdated"))
      await loadMembers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("roleUpdateFailed"))
    } finally {
      setSavingId(null)
    }
  }

  const handleToggleDisabled = async (user: MemberUser) => {
    if (resolveTeamRole(user) === "owner" && ownerCount <= 1 && !user.banned) {
      toast.error(t("lastOwner"))
      return
    }

    setSavingId(user.id)
    try {
      await requestTeamMembers<{ user: MemberUser }>({
        method: "PATCH",
        body: JSON.stringify({
          action: "disabled",
          userId: user.id,
          disabled: !user.banned,
        }),
      })
      toast.success(user.banned ? t("enabled") : t("disabled"))
      await loadMembers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("statusUpdateFailed"))
    } finally {
      setSavingId(null)
    }
  }

  const handleRevokeSessions = async (userId: string) => {
    setSavingId(userId)
    try {
      const result = await authClient.admin.revokeUserSessions({ userId })
      assertAuthSuccess(result)
      toast.success(t("sessionsRevoked"))
    } catch {
      toast.error(t("sessionsRevokeFailed"))
    } finally {
      setSavingId(null)
    }
  }

  const handleResetPassword = async () => {
    if (!passwordResetUser) {
      return
    }

    setSavingId(passwordResetUser.id)
    try {
      await requestTeamMembers<{ user: MemberUser }>({
        method: "PATCH",
        body: JSON.stringify({
          action: "password",
          userId: passwordResetUser.id,
          password: resetPassword,
        }),
      })
      toast.success(t("passwordReset"))
      setPasswordResetUser(null)
      setResetPassword("")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("passwordResetFailed"))
    } finally {
      setSavingId(null)
    }
  }

  return (
    <>
      <section className="space-y-4">
        <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1.5">
            <h3 className="text-lg font-semibold tracking-[-0.015em] text-foreground">
              {t("title")}
            </h3>
            <p className="max-w-[65ch] text-sm leading-6 text-muted-foreground">
              {t("description")}
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)} className="rounded-md">
            {t("createCta")}
          </Button>
        </header>

        <div className="overflow-hidden rounded-xl border border-border/70 bg-card">
          {loading ? (
            <div className="flex items-center gap-2 px-5 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {t("loading")}
            </div>
          ) : members.length === 0 ? (
            <div className="px-5 py-6 text-sm text-muted-foreground">
              {t("empty")}
            </div>
          ) : (
            members.map((member) => {
              const memberRole = resolveTeamRole(member)
              const isLastOwner = memberRole === "owner" && ownerCount <= 1
              const isSelf = member.id === viewerId
              const icon =
                memberRole === "owner" ? (
                  <ShieldCheck className="size-4" />
                ) : memberRole === "admin" ? (
                  <Shield className="size-4" />
                ) : (
                  <UserRound className="size-4" />
                )

              return (
                <div
                  key={member.id}
                  className="border-b border-border/60 px-5 py-4 last:border-b-0"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-foreground">{member.name}</p>
                        <Badge variant="outline" className="rounded-md">
                          <span className="flex items-center gap-1">
                            {icon}
                            {t(`roles.${memberRole}`)}
                          </span>
                        </Badge>
                        {member.banned ? (
                          <Badge variant="destructive" className="rounded-md">
                            {t("disabledBadge")}
                          </Badge>
                        ) : null}
                        {isSelf ? (
                          <Badge variant="secondary" className="rounded-md">
                            {t("you")}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="text-sm text-muted-foreground">{member.email}</p>
                    </div>

                    <div className="flex flex-col gap-3 lg:min-w-[360px]">
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <Select
                          value={memberRole}
                          onValueChange={(value) =>
                            void handleRoleChange(member, value as TeamRole)
                          }
                          disabled={savingId === member.id || (isLastOwner && isSelf)}
                        >
                          <SelectTrigger className="h-10 w-full rounded-md bg-background sm:w-[160px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {ALL_TEAM_ROLES.map((role) => (
                              <SelectItem
                                key={role}
                                value={role}
                                disabled={role === "owner" && !canManageOwnerRole}
                              >
                                {t(`roles.${role}`)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>

                        <Button
                          type="button"
                          variant={member.banned ? "outline" : "secondary"}
                          className="h-10 rounded-md"
                          onClick={() => void handleToggleDisabled(member)}
                          disabled={savingId === member.id || isLastOwner}
                        >
                          <Ban className="size-4" />
                          {member.banned ? t("enable") : t("disable")}
                        </Button>
                      </div>

                      <div className="flex flex-col gap-2 sm:flex-row">
                        {authLocalEnabled ? (
                          <Button
                            type="button"
                            variant="outline"
                            className="h-10 rounded-md"
                            onClick={() => setPasswordResetUser(member)}
                            disabled={savingId === member.id}
                          >
                            <KeyRound className="size-4" />
                            {t("resetPassword")}
                          </Button>
                        ) : null}

                        <Button
                          type="button"
                          variant="outline"
                          className="h-10 rounded-md"
                          onClick={() => void handleRevokeSessions(member.id)}
                          disabled={savingId === member.id}
                        >
                          {t("revokeSessions")}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </section>

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) {
            setCreateError(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("createTitle")}</DialogTitle>
            <DialogDescription>{t("createDescription")}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="member-name">{t("fields.name")}</Label>
              <Input
                id="member-name"
                value={createForm.name}
                onChange={(event) =>
                  setCreateForm((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="member-email">{t("fields.email")}</Label>
              <Input
                id="member-email"
                type="email"
                value={createForm.email}
                onChange={(event) =>
                  setCreateForm((current) => ({
                    ...current,
                    email: event.target.value,
                  }))
                }
              />
            </div>

            {authLocalEnabled ? (
              <div className="space-y-2">
                <Label htmlFor="member-password">{t("fields.password")}</Label>
                <Input
                  id="member-password"
                  type="password"
                  value={createForm.password}
                  onChange={(event) =>
                    setCreateForm((current) => ({
                      ...current,
                      password: event.target.value,
                    }))
                  }
                />
              </div>
            ) : null}

            <div className="space-y-2">
              <Label>{t("fields.role")}</Label>
              <Select
                value={createForm.teamRole}
                onValueChange={(value) =>
                  setCreateForm((current) => ({
                    ...current,
                    teamRole: value as TeamRole,
                  }))
                }
              >
                <SelectTrigger className="w-full" aria-label={t("fields.role")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ALL_TEAM_ROLES.map((role) => (
                    <SelectItem
                      key={role}
                      value={role}
                      disabled={role === "owner" && !canManageOwnerRole}
                    >
                      {t(`roles.${role}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {createError ? (
              <p className="text-sm text-destructive" role="alert">
                {createError}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("cancel")}
            </Button>
            <Button
              onClick={() => void handleCreateUser()}
              disabled={
                creating ||
                !createForm.name ||
                !createForm.email ||
                (authLocalEnabled && !createForm.password)
              }
            >
              {creating ? <Loader2 className="size-4 animate-spin" /> : null}
              {t("createAction")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(passwordResetUser)}
        onOpenChange={(open) => {
          if (!open) {
            setPasswordResetUser(null)
            setResetPassword("")
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("resetTitle")}</DialogTitle>
            <DialogDescription>
              {passwordResetUser
                ? t("resetDescription", { email: passwordResetUser.email })
                : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="reset-password">{t("fields.password")}</Label>
            <Input
              id="reset-password"
              type="password"
              value={resetPassword}
              onChange={(event) => setResetPassword(event.target.value)}
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setPasswordResetUser(null)
                setResetPassword("")
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              onClick={() => void handleResetPassword()}
              disabled={!resetPassword}
            >
              {t("resetAction")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
