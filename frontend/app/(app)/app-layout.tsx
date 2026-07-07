"use client"

import type React from "react"

import { useCallback, useEffect, useState } from "react"
import dynamic from "next/dynamic"
import { usePathname } from "next/navigation"
import { useTranslations } from "next-intl"
import { TerminalSquare } from "lucide-react"
import { BreadcrumbProvider } from "@/components/bioinfoflow/breadcrumb-context"
import { Navbar } from "@/components/bioinfoflow/navbar"
import { ProjectProvider } from "@/components/bioinfoflow/project-context"
import { Sidebar } from "@/components/bioinfoflow/sidebar/index"
import { SidebarDrawer } from "@/components/bioinfoflow/sidebar/sidebar-drawer"
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
import type { ViewerIdentity } from "@/lib/auth-config"
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
  const tAccessibility = useTranslations("accessibility")
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
  const selectWorkspaceProject = useCallback((projectId: string) => {
    setSelectedProjectId(projectId)
    setConversationProjectId(projectId)
    setActiveConversationId("")
  }, [])
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

  const effectiveLeftWidth = leftSidebarCollapsed ? LEFT_SIDEBAR_COLLAPSED : leftSidebarWidth

  return (
    <RuntimeProvider mode={runtimeMode}>
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
              <TerminalHotkeys enabled={terminalEnabled} />
              {/* Skip-to-content link */}
              <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg"
              >
                Skip to content
              </a>

              <div className="flex min-h-[100dvh] bg-background text-foreground">
                {/* Left Sidebar - Desktop */}
                {!isMobile && (
                  <nav
                    className="relative flex-shrink-0 transition-[width,opacity] duration-200"
                    style={{ width: effectiveLeftWidth }}
                    role="navigation"
                    aria-label="Project navigation"
                  >
                    <div
                      className="fixed inset-y-0 left-0 z-20 h-[100dvh] transition-[width,opacity] duration-200"
                      style={{ opacity: 1, width: effectiveLeftWidth }}
                    >
                      <Sidebar
                        collapsed={leftSidebarCollapsed}
                        onCollapsedChange={setLeftSidebarCollapsed}
                        onCommandOpen={toggleCommandPalette}
                        viewer={viewer}
                        runtimeMode={runtimeMode}
                      />
                      {!leftSidebarCollapsed && (
                        <ResizeHandle side="left" onResize={handleLeftResize} />
                      )}
                    </div>
                  </nav>
                )}

                {/* Left Sidebar - Mobile Drawer */}
                {isMobile && (
                  <SidebarDrawer open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
                    <Sidebar
                      collapsed={false}
                      onCommandOpen={toggleCommandPalette}
                      viewer={viewer}
                      runtimeMode={runtimeMode}
                    />
                  </SidebarDrawer>
                )}

                {/* Main Content Area */}
                <div
                  className="flex min-h-[100dvh] min-w-0 flex-1 flex-col bg-background"
                  style={{
                    "--left-rail-compensation":
                      !isMobile && leftSidebarCollapsed
                        ? `${effectiveLeftWidth / 2}px`
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

function TerminalHotkeys({ enabled }: { enabled: boolean }) {
  const { toggleTerminal } = useTerminalDock()

  useEffect(() => {
    if (!enabled) return

    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault()
        toggleTerminal()
      }
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [enabled, toggleTerminal])

  return null
}
