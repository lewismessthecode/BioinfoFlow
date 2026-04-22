"use client"

import { Component, type ReactNode } from "react"
import { useTranslations } from "next-intl"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { logger } from "@/lib/logger"

const MAX_RETRIES = 3

interface ChatErrorBoundaryProps {
  children: ReactNode
  /** Label shown in the fallback UI to describe what crashed */
  label?: string
}

interface ChatErrorBoundaryState {
  hasError: boolean
  error: Error | null
  retryCount: number
}

interface ChatErrorFallbackProps {
  label?: string
  errorMessage?: string
  exhausted: boolean
  remaining: number
  onRetry: () => void
}

function ChatErrorFallback({
  label,
  errorMessage,
  exhausted,
  remaining,
  onRetry,
}: ChatErrorFallbackProps) {
  const t = useTranslations("chat.errorBoundary")
  return (
    <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 my-1">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-destructive mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-destructive">
            {label ? t("failedToRender", { label }) : t("genericError")}
          </p>
          {errorMessage && (
            <p className="mt-1 text-xs text-muted-foreground truncate">
              {errorMessage}
            </p>
          )}
          {exhausted ? (
            <p className="mt-2 text-xs text-muted-foreground/70">
              {t("exhausted", { count: MAX_RETRIES })}
            </p>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-6 px-2 text-xs text-muted-foreground"
              onClick={onRetry}
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              {t("retry", { remaining })}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Granular error boundary for chat-related components.
 *
 * Catches rendering errors in message bubbles, DAG panels, and
 * markdown renderers so the entire page doesn't crash.
 * Caps retries at 3 to prevent infinite loops on permanently broken content.
 */
export class ChatErrorBoundary extends Component<
  ChatErrorBoundaryProps,
  ChatErrorBoundaryState
> {
  constructor(props: ChatErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, retryCount: 0 }
  }

  static getDerivedStateFromError(error: Error): Partial<ChatErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    logger.error(
      `[ChatErrorBoundary${this.props.label ? `: ${this.props.label}` : ""}]`,
      { error, componentStack: info.componentStack },
    )
  }

  private handleRetry = () => {
    this.setState((prev) => ({
      hasError: false,
      error: null,
      retryCount: prev.retryCount + 1,
    }))
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <ChatErrorFallback
          label={this.props.label}
          errorMessage={this.state.error?.message}
          exhausted={this.state.retryCount >= MAX_RETRIES}
          remaining={MAX_RETRIES - this.state.retryCount}
          onRetry={this.handleRetry}
        />
      )
    }

    return this.props.children
  }
}
