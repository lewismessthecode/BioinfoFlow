"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { Loader2, LockKeyhole, Mail } from "lucide-react"
import { authClient } from "@/lib/auth-client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const SIGN_IN_TIMEOUT_MS = 15000

type SubmitState = "idle" | "loading" | "success" | "error" | "timeout"

export function EmailSignInForm() {
  const t = useTranslations("auth")
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitState, setSubmitState] = useState<SubmitState>("idle")
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setSubmitState("loading")

    const signInPromise = authClient.signIn.email({
      email,
      password,
      callbackURL: "/agent",
      fetchOptions: {
        onSuccess: () => {
          setSubmitState("success")
          router.replace("/agent")
          router.refresh()
        },
      },
    })

    try {
      const result = await Promise.race([
        signInPromise,
        new Promise<{ timedOut: true }>((resolve) =>
          setTimeout(() => resolve({ timedOut: true }), SIGN_IN_TIMEOUT_MS),
        ),
      ])

      if ("timedOut" in result) {
        setError(t("local.timeoutMessage"))
        setSubmitState("timeout")
        return
      }

      if (result?.error) {
        setError(t("local.errorMessage"))
        setSubmitState("error")
        return
      }

      setSubmitState("idle")
    } catch {
      setError(t("local.errorMessage"))
      setSubmitState("error")
    }
  }

  const submitting = submitState === "loading"

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <div className="space-y-1.5">
        <Label htmlFor="email">{t("local.emailLabel")}</Label>
        <div className="relative">
          <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t("local.emailPlaceholder")}
            className="h-10 rounded-xl pl-10"
            required
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="password">{t("local.passwordLabel")}</Label>
        <div className="relative">
          <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={t("local.passwordPlaceholder")}
            className="h-10 rounded-xl pl-10"
            required
          />
        </div>
      </div>

      <Button
        type="submit"
        disabled={submitting}
        className="h-10 w-full rounded-xl text-sm font-semibold"
      >
        {submitting ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            {t("local.submitting")}
          </>
        ) : (
          t("local.submit")
        )}
      </Button>

      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}
