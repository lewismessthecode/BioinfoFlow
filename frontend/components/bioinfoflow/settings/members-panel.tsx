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
} from "lucide-react"
import { authClient } from "@/lib/auth-client"
import { toBetterAuthRole } from "@/lib/auth-config"
import type { TeamRole } from "@/lib/auth-config"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
      const result = await authClient.admin.listUsers({
        query: {
          limit: 100,
          sortBy: "createdAt",
          sortDirection: "asc",
        },
      })
      const data = assertAuthSuccess(result)
      setMembers(((data as { users?: MemberUser[] } | null)?.users) ?? [])
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
    try {
      const result = await authClient.admin.createUser({
        email: createForm.email,
        name: createForm.name,
        password: authLocalEnabled ? createForm.password : undefined,
        role: toBetterAuthRole(createForm.teamRole),
        data: {
          teamRole: createForm.teamRole,
        },
      })
      assertAuthSuccess(result)
      toast.success(t("created"))
      setCreateOpen(false)
      setCreateForm({
        name: "",
        email: "",
        password: "",
        teamRole: "member",
      })
      await loadMembers()
    } catch {
      toast.error(t("createFailed"))
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
      const result = await authClient.admin.updateUser({
        userId: user.id,
        data: {
          role: toBetterAuthRole(nextRole),
          teamRole: nextRole,
        },
      })
      assertAuthSuccess(result)
      toast.success(t("roleUpdated"))
      await loadMembers()
    } catch {
      toast.error(t("roleUpdateFailed"))
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
      if (user.banned) {
        const result = await authClient.admin.unbanUser({ userId: user.id })
        assertAuthSuccess(result)
      } else {
        const result = await authClient.admin.banUser({
          userId: user.id,
          banReason: "Disabled by administrator",
        })
        assertAuthSuccess(result)
      }
      toast.success(user.banned ? t("enabled") : t("disabled"))
      await loadMembers()
    } catch {
      toast.error(t("statusUpdateFailed"))
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
      const result = await authClient.admin.setUserPassword({
        userId: passwordResetUser.id,
        newPassword: resetPassword,
      })
      assertAuthSuccess(result)
      toast.success(t("passwordReset"))
      setPasswordResetUser(null)
      setResetPassword("")
    } catch {
      toast.error(t("passwordResetFailed"))
    } finally {
      setSavingId(null)
    }
  }

  return (
    <>
      <Card className="border-border/60 bg-card/95 shadow-sm">
        <CardHeader className="gap-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <CardTitle>{t("title")}</CardTitle>
              <CardDescription>{t("description")}</CardDescription>
            </div>
            <Button onClick={() => setCreateOpen(true)} className="rounded-2xl">
              {t("createCta")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              {t("loading")}
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
                  className="rounded-[24px] border border-border/60 bg-[color:var(--surface-subtle)] p-4"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-foreground">{member.name}</p>
                        <Badge variant="outline" className="rounded-full">
                          <span className="flex items-center gap-1">
                            {icon}
                            {t(`roles.${memberRole}`)}
                          </span>
                        </Badge>
                        {member.banned ? (
                          <Badge variant="destructive" className="rounded-full">
                            {t("disabledBadge")}
                          </Badge>
                        ) : null}
                        {isSelf ? (
                          <Badge variant="secondary" className="rounded-full">
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
                          <SelectTrigger className="h-10 w-full rounded-2xl bg-background sm:w-[160px]">
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
                          className="h-10 rounded-2xl"
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
                            className="h-10 rounded-2xl"
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
                          className="h-10 rounded-2xl"
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
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
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
                <SelectTrigger className="w-full">
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
