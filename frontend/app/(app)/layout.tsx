import { headers } from "next/headers"
import { redirect } from "next/navigation"

import { ensureAuthReady, getAuth } from "@/lib/auth"
import {
  buildAnonymousViewer,
  buildViewerIdentity,
  getServerAuthConfig,
} from "@/lib/auth-config"
import AppLayout from "./app-layout"
import "./app-shell.css"

export default async function ProtectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const authConfig = getServerAuthConfig()
  if (!authConfig.authEnabled) {
    return <AppLayout viewer={buildAnonymousViewer()}>{children}</AppLayout>
  }

  await ensureAuthReady()
  const auth = await getAuth()
  if (!auth) {
    return <AppLayout viewer={buildAnonymousViewer()}>{children}</AppLayout>
  }
  const session = await auth.api.getSession({
    headers: await headers(),
  })

  if (!session) {
    redirect("/auth")
  }

  return (
    <AppLayout
      viewer={buildViewerIdentity(session.user, authConfig)}
    >
      {children}
    </AppLayout>
  )
}
