"use client"

import type React from "react"

import { useCallback, useEffect, useMemo, useState } from "react"
import dynamic from "next/dynamic"
import { usePathname, useSearchParams } from "next/navigation"
import { useTranslations } from "next-intl"
import { TerminalSquare } from "@/lib/icons"
import { BreadcrumbProvider } from "@/components/bioinfoflow/breadcrumb-context"
import { Navbar } from "@/components/bioinfoflow/navbar"
import { ProjectProvider } from "@/components/bioinfoflow/project-context"
import { SettingsSidebar, Sidebar } from "@/components/bioinfoflow/sidebar/index"
import { SidebarDrawer } from "@/components/bioinfoflow/sidebar/sidebar-drawer"
import {
  canManageMembers as canManageMembersHelper,
  canManageRegistryCatalog,
} from "@/lib/auth-config"
import { writeSettingsReturnPath } from "@/lib/settings-return-path"
import {
  isSettingsSectionKey,
  type SettingsSectionKey,
} from "@/lib/settings-nav"
import {
  useWorkspaceShell,
  WorkspaceShellProvider,
} from "@/components/bioinfoflow/workspace-shell-context"
import {
  TerminalDockProvider,
  useTerminalDock,
} from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import {
  FirstRunProvider,
  useFirstRun,
} from "@/hooks/use-first-run"
import type { ViewerIdentity } from "@/lib/auth-config"
import {
  firstRunActivationStorageKey,
  LAST_USED_PROJECT_STORAGE_KEY,
} from "@/lib/first-run"
import { RuntimeProvider, getActiveRuntime, type RuntimeMode } from "@/lib/runtime"

const LEFT_SIDEBAR_MIN = 240
const LEFT_SIDEBAR_MAX = 420
const LEFT_SIDEBAR_DEFAULT = 300
const LEFT_SIDEBAR_COLLAPSED = 56

const LazyCommandPalette = dynamic(
  () => import("@/components/bioinfoflow/command-palette").then((m) => ({ default: m.CommandPalette })),
  { ssr: false },
)

const LazyTerminalDock = dynamic(
  () => import("@/components/bioinfoflow/terminal/terminal-dock").then((m) => ({ default: m.TerminalDock })),
  { ssr: false },
)

type AppLayoutProps = {
  children: React.ReactNode
  viewer?: ViewerIdentity
  runtimeMode?: RuntimeMode
}

export default function AppLayout({
  children,
  viewer,
  runtimeMode = "live",
}: AppLayoutProps) {
  const runtime = getActiveRuntime(runtimeMode)
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const tAccessibility = useTranslations("accessibility")
  const isSettingsRoute =
    pathname === "/settings" || pathname.startsWith("/settings/")
  const canManageMembersFlag = viewer
    ? canManageMembersHelper(viewer.mode, viewer.role, viewer.authEnabled)
    : false
  const canManageRegistriesFlag = viewer
    ? canManageRegistryCatalog(viewer.mode, viewer.role, viewer.authEnabled)
    : true
  const activeSettingsSection: SettingsSectionKey = useMemo(() => {
    const raw = searchParams?.get("section") ?? null
    if (!isSettingsSectionKey(raw)) return "account"
    if (raw === "members" && !canManageMembersFlag) return "account"
    if (raw === "registries" && !canManageRegistriesFlag) return "account"
    return raw
  }, [searchParams, canManageMembersFlag, canManageRegistriesFlag])
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(LEFT_SIDEBAR_DEFAULT)
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState(
    runtime.contextDefaults?.selectedProjectId ?? "",
  )
  const [conversationProjectId, setConversationProjectId] = useState(
    runtime.contextDefaults?.selectedProjectId ?? "",
  )
  const [activeConversationId, setActiveConversationId] = useState("")
  const [activeProjectName, setActiveProjectName] = useState("")
  const [activeConversationTitle, setActiveConversationTitle] = useState("")
  const [commandOpen, setCommandOpen] = useState(false)
  const [commandPaletteMounted, setCommandPaletteMounted] = useState(false)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const [sidebarPrefsLoaded, setSidebarPrefsLoaded] = useState(false)
  const isMobile = useIsMobile()
  const onAgentRoute = pathname === "/agent" || pathname.startsWith("/agent/")
  const firstRun = useFirstRun(runtimeMode === "live" && onAgentRoute)
  const selectWorkspaceProject = useCallback((projectId: string) => {
    setSelectedProjectId(projectId)
    setConversationProjectId(projectId)
    setActiveConversationId("")
  }, [])

  useEffect(() => {
    const data = firstRun.data
    const demoProjectId = data?.demo_project_id
    if (!data?.ready || !demoProjectId) return

    const activationKey = firstRunActivationStorageKey(demoProjectId)
    if (localStorage.getItem(activationKey)) return

    const rememberedProjectId = localStorage.getItem(
      LAST_USED_PROJECT_STORAGE_KEY,
    )
    if (
      selectedProjectId ||
      conversationProjectId ||
      rememberedProjectId
    ) {
      return
    }
    const timer = window.setTimeout(() => {
      selectWorkspaceProject(demoProjectId)
      localStorage.setItem(activationKey, "true")
    }, 0)
    return () => window.clearTimeout(timer)
  }, [
    conversationProjectId,
    firstRun.data,
    selectWorkspaceProject,
    selectedProjectId,
  ])
  const terminalEnabled =
    runtime.capabilities.terminal &&
    Boolean(selectedProjectId) &&
    (pathname === "/agent" ||
      pathname.startsWith("/agent/") ||
      pathname === "/runs" ||
      pathname.startsWith("/runs/"))

  // Load persisted state from localStorage (runs once after hydration)
  useEffect(() => {
    const savedWidth = localStorage.getItem("left-sidebar-width")
    const savedCollapsed = localStorage.getItem("left-sidebar-collapsed")
    /* eslint-disable react-hooks/set-state-in-effect */
    if (savedWidth) setLeftSidebarWidth(Number(savedWidth))
    if (savedCollapsed) setLeftSidebarCollapsed(savedCollapsed === "true")
    setSidebarPrefsLoaded(true)
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [])

  // Persist state
  useEffect(() => {
    if (!sidebarPrefsLoaded) return
    localStorage.setItem("left-sidebar-width", String(leftSidebarWidth))
  }, [leftSidebarWidth, sidebarPrefsLoaded])

  useEffect(() => {
    if (!sidebarPrefsLoaded) return
    localStorage.setItem("left-sidebar-collapsed", String(leftSidebarCollapsed))
  }, [leftSidebarCollapsed, sidebarPrefsLoaded])

  const handleLeftResize = useCallback((delta: number) => {
    setLeftSidebarWidth((prev) => {
      const next = prev + delta
      return Math.min(LEFT_SIDEBAR_MAX, Math.max(LEFT_SIDEBAR_MIN, next))
    })
  }, [])

  const toggleLeftSidebar = useCallback(() => {
    if (isMobile) {
      setMobileDrawerOpen((prev) => !prev)
    } else {
      setLeftSidebarCollapsed((prev) => !prev)
    }
  }, [isMobile])

  const handleCommandOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      setCommandPaletteMounted(true)
    }
    setCommandOpen(nextOpen)
  }, [])

  const toggleCommandPalette = useCallback(() => {
    setCommandPaletteMounted(true)
    setCommandOpen((prev) => !prev)
  }, [])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        toggleCommandPalette()
      }
      // Toggle left sidebar with Cmd+B
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") {
        event.preventDefault()
        toggleLeftSidebar()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [toggleCommandPalette, toggleLeftSidebar])

  useEffect(() => {
    if (!isSettingsRoute) {
      writeSettingsReturnPath(pathname)
    }
  }, [isSettingsRoute, pathname])

  const workspaceLeftWidth = leftSidebarCollapsed
    ? LEFT_SIDEBAR_COLLAPSED
    : leftSidebarWidth
  const effectiveLeftWidth = isSettingsRoute
    ? LEFT_SIDEBAR_DEFAULT
    : workspaceLeftWidth
  const showResizeHandle = !isSettingsRoute && !leftSidebarCollapsed
  const renderSidebar = (mobile: boolean) =>
    isSettingsRoute ? (
      <SettingsSidebar
        activeSection={activeSettingsSection}
        viewer={viewer}
        canManageMembers={canManageMembersFlag}
        canManageRegistries={canManageRegistriesFlag}
      />
    ) : (
      <Sidebar
        collapsed={mobile ? false : leftSidebarCollapsed}
        onCollapsedChange={mobile ? undefined : setLeftSidebarCollapsed}
        onCommandOpen={toggleCommandPalette}
        viewer={viewer}
        runtimeMode={runtimeMode}
      />
    )

  return (
    <RuntimeProvider mode={runtimeMode}>
      <FirstRunProvider value={firstRun.data} isLoading={firstRun.isLoading}>
        <ProjectProvider
        value={{
          selectedProjectId,
          setSelectedProjectId,
          conversationProjectId,
          setConversationProjectId,
          activeProjectId: selectedProjectId,
          setActiveProjectId: selectWorkspaceProject,
          selectWorkspaceProject,
          activeConversationId,
          setActiveConversationId,
          activeProjectName,
          setActiveProjectName,
          activeConversationTitle,
          setActiveConversationTitle,
        }}
      >
        <WorkspaceShellProvider>
          <BreadcrumbProvider>
            <TerminalDockProvider
              projectId={selectedProjectId || undefined}
              enabled={terminalEnabled}
              isMobile={isMobile}
            >
              {/* Skip-to-content link */}
              <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg"
              >
                Skip to content
              </a>

              <div className="flex h-[100dvh] overflow-hidden bg-background text-foreground">
                {/* Left Sidebar - Desktop */}
                {!isMobile && (
                  <nav
                    className="relative flex-shrink-0 transition-[width,opacity] duration-200"
                    style={{ width: effectiveLeftWidth }}
                    role="navigation"
                    aria-label={isSettingsRoute ? "Settings sidebar" : "Project navigation"}
                  >
                    <div
                      className="fixed inset-y-0 left-0 z-20 h-[100dvh] transition-[width,opacity] duration-200"
                      style={{ opacity: 1, width: effectiveLeftWidth }}
                    >
                      {renderSidebar(false)}
                      {showResizeHandle && (
                        <ResizeHandle side="left" onResize={handleLeftResize} />
                      )}
                    </div>
                  </nav>
                )}

                {/* Left Sidebar - Mobile Drawer */}
                {isMobile && (
                  <SidebarDrawer open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
                    {renderSidebar(true)}
                  </SidebarDrawer>
                )}

                {/* Main Content Area */}
                  <div
                    className="flex h-[100dvh] min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
                  style={{
                    "--left-rail-compensation":
                      !isMobile && !isSettingsRoute && leftSidebarCollapsed
                        ? `${workspaceLeftWidth / 2}px`
                        : "0px",
                  } as React.CSSProperties}
                >
                  <Navbar
                    onSidebarToggle={toggleLeftSidebar}
                    showHamburger={isMobile}
                    projectName={activeProjectName}
                    conversationTitle={activeConversationTitle}
                    viewer={viewer}
                  >
                    {terminalEnabled ? (
                      <TerminalNavbarAction label={tAccessibility("openTerminal")} />
                    ) : null}
                    <WorkspaceNavbarActions />
                  </Navbar>
                  <main id="main-content" className="min-h-0 flex-1 overflow-hidden" role="main">
                    {children}
                  </main>
                  {terminalEnabled ? <LazyTerminalDock /> : null}
                </div>
              </div>
              {commandPaletteMounted ? (
                <LazyCommandPalette open={commandOpen} onOpenChange={handleCommandOpenChange} />
              ) : null}
              <Toaster position="bottom-right" />
            </TerminalDockProvider>
          </BreadcrumbProvider>
        </WorkspaceShellProvider>
        </ProjectProvider>
      </FirstRunProvider>
    </RuntimeProvider>
  )
}

function WorkspaceNavbarActions() {
  const { navbarActions } = useWorkspaceShell()
  return navbarActions
}

function TerminalNavbarAction({ label }: { label: string }) {
  const { toggleTerminal } = useTerminalDock()

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 rounded-lg border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"
      onClick={toggleTerminal}
      aria-label={label}
    >
      <TerminalSquare className="h-4 w-4" />
    </Button>
  )
}
