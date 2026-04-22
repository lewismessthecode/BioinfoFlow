"use client"

import type React from "react"

import { useCallback, useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { useTranslations } from "next-intl"
import { TerminalSquare } from "lucide-react"
import { BreadcrumbProvider } from "@/components/bioinfoflow/breadcrumb-context"
import { CommandPalette } from "@/components/bioinfoflow/command-palette"
import { Navbar } from "@/components/bioinfoflow/navbar"
import { ProjectProvider } from "@/components/bioinfoflow/project-context"
import { Sidebar } from "@/components/bioinfoflow/sidebar/index"
import { SidebarDrawer } from "@/components/bioinfoflow/sidebar/sidebar-drawer"
import { TerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock"
import { WorkspaceShellProvider } from "@/components/bioinfoflow/workspace-shell-context"
import {
  TerminalDockProvider,
  useTerminalDock,
} from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import type { ViewerIdentity } from "@/lib/auth-config"

const LEFT_SIDEBAR_MIN = 200
const LEFT_SIDEBAR_MAX = 400
const LEFT_SIDEBAR_DEFAULT = 260
const LEFT_SIDEBAR_COLLAPSED = 56

type AppLayoutProps = {
  children: React.ReactNode
  viewer?: ViewerIdentity
}

export default function AppLayout({ children, viewer }: AppLayoutProps) {
  const pathname = usePathname()
  const tAccessibility = useTranslations("accessibility")
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(LEFT_SIDEBAR_DEFAULT)
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState("")
  const [conversationProjectId, setConversationProjectId] = useState("")
  const [activeConversationId, setActiveConversationId] = useState("")
  const [activeProjectName, setActiveProjectName] = useState("")
  const [activeConversationTitle, setActiveConversationTitle] = useState("")
  const [commandOpen, setCommandOpen] = useState(false)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const isMobile = useIsMobile()
  const terminalEnabled =
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
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [])

  // Persist state
  useEffect(() => {
    localStorage.setItem("left-sidebar-width", String(leftSidebarWidth))
  }, [leftSidebarWidth])

  useEffect(() => {
    localStorage.setItem("left-sidebar-collapsed", String(leftSidebarCollapsed))
  }, [leftSidebarCollapsed])

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

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setCommandOpen((prev) => !prev)
      }
      // Toggle left sidebar with Cmd+B
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") {
        event.preventDefault()
        toggleLeftSidebar()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [toggleLeftSidebar])

  const effectiveLeftWidth = leftSidebarCollapsed ? LEFT_SIDEBAR_COLLAPSED : leftSidebarWidth

  return (
    <ProjectProvider
      value={{
        selectedProjectId,
        setSelectedProjectId,
        conversationProjectId,
        setConversationProjectId,
        activeProjectId: selectedProjectId,
        setActiveProjectId: setSelectedProjectId,
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

            <div className="flex h-screen bg-background">
              {/* Left Sidebar - Desktop */}
              {!isMobile && (
                <nav
                  className="relative flex-shrink-0 transition-[width,opacity] duration-200"
                  style={{ width: effectiveLeftWidth }}
                  role="navigation"
                  aria-label="Project navigation"
                >
                  <div
                    className="h-full transition-opacity duration-200"
                    style={{ opacity: leftSidebarCollapsed ? 0.7 : 1 }}
                  >
                    <Sidebar
                      collapsed={leftSidebarCollapsed}
                      onCollapsedChange={setLeftSidebarCollapsed}
                      viewer={viewer}
                    />
                  </div>
                  {!leftSidebarCollapsed && (
                    <ResizeHandle side="left" onResize={handleLeftResize} />
                  )}
                </nav>
              )}

              {/* Left Sidebar - Mobile Drawer */}
              {isMobile && (
                <SidebarDrawer open={mobileDrawerOpen} onOpenChange={setMobileDrawerOpen}>
                  <Sidebar collapsed={false} viewer={viewer} />
                </SidebarDrawer>
              )}

              {/* Main Content Area */}
              <div className="flex-1 flex flex-col min-w-0">
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
                </Navbar>
                <main id="main-content" className="min-h-0 flex-1 overflow-hidden" role="main">
                  {children}
                </main>
                <TerminalDock />
              </div>
            </div>
            <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
            <Toaster position="bottom-right" />
          </TerminalDockProvider>
        </BreadcrumbProvider>
      </WorkspaceShellProvider>
    </ProjectProvider>
  )
}

function TerminalNavbarAction({ label }: { label: string }) {
  const { toggleTerminal } = useTerminalDock()

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-9 w-9 rounded-xl border border-transparent text-foreground/82 transition-colors hover:border-border/70 hover:bg-accent hover:text-foreground"
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
