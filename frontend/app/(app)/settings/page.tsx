import { headers } from "next/headers"
import SettingsPageClient from "@/components/bioinfoflow/settings/settings-page-client"
import { ensureAuthReady, getAuth } from "@/lib/auth"
import {
  buildAnonymousViewer,
  buildViewerIdentity,
  getServerAuthConfig,
} from "@/lib/auth-config"

export default async function SettingsPage() {
  const authConfig = getServerAuthConfig()

  if (!authConfig.authEnabled) {
    const viewer = buildAnonymousViewer()
    return (
      <SettingsPageClient
        viewer={{
          id: viewer.id,
          name: viewer.name,
          email: viewer.email,
          role: viewer.role,
          mode: viewer.mode,
          canManageMembers: viewer.canManageMembers,
          authEnabled: false,
          authLocalEnabled: authConfig.authLocalEnabled,
        }}
      />
    )
  }

  await ensureAuthReady()
  const auth = await getAuth()
  if (!auth) {
    const viewer = buildAnonymousViewer()
    return (
      <SettingsPageClient
        viewer={{
          id: viewer.id,
          name: viewer.name,
          email: viewer.email,
          role: viewer.role,
          mode: viewer.mode,
          canManageMembers: viewer.canManageMembers,
          authEnabled: viewer.authEnabled,
          authLocalEnabled: authConfig.authLocalEnabled,
        }}
      />
    )
  }
  const session = await auth.api.getSession({
    headers: await headers(),
  })
  const viewer = session?.user
    ? buildViewerIdentity(session.user, authConfig)
    : buildAnonymousViewer()

  return (
    <SettingsPageClient
      viewer={{
        id: viewer.id,
        name: viewer.name,
        email: viewer.email,
        role: viewer.role,
        mode: viewer.mode,
        canManageMembers: viewer.canManageMembers,
        authEnabled: viewer.authEnabled,
        authLocalEnabled: authConfig.authLocalEnabled,
      }}
    />
  )
}
